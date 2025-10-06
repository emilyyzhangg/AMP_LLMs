import requests, time, xml.etree.ElementTree as ET, json
from pathlib import Path
DEFAULT_TIMEOUT=15
SLEEP=0.34
CTG_V2_BASE='https://clinicaltrials.gov/api/v2/studies'
CTG_LEGACY_FULL='https://clinicaltrials.gov/api/query/full_studies'

def fetch_clinical_trial_data(nct):
    nct=nct.strip().upper()
    url=f"{CTG_V2_BASE}/{nct}"
    try:
        r=requests.get(url, timeout=DEFAULT_TIMEOUT)
        if r.status_code==200:
            return {'nct_id': nct, 'clinical_trial_data': r.json(), 'source':'clinicaltrials_v2_detail'}
        elif r.status_code==404:
            pass
    except Exception as e:
        pass
    try:
        params={'expr':nct,'min_rnk':1,'max_rnk':1,'fmt':'json'}
        r=requests.get(CTG_LEGACY_FULL, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data=r.json()
        studies=data.get('FullStudiesResponse',{}).get('FullStudies',[])
        if studies:
            return {'nct_id':nct,'clinical_trial_data':studies[0].get('Study',{}),'source':'clinicaltrials_legacy_full'}
        return {'error':f'No study for {nct}','source':'clinicaltrials_not_found'}
    except Exception as e:
        return {'error':str(e),'source':'clinicaltrials_error'}

# PubMed/PMC utils (abbreviated versions)
def fetch_pubmed_by_pmid(pmid):
    url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi'
    params={'db':'pubmed','id':pmid,'retmode':'xml'}
    try:
        r=requests.get(url, params=params, timeout=DEFAULT_TIMEOUT); r.raise_for_status()
        root=ET.fromstring(r.text)
        art=root.find('.//PubmedArticle')
        if art is None: return {'error':'no article','pmid':pmid}
        title=art.findtext('.//ArticleTitle','')
        abstract=''.join([t.text or '' for t in art.findall('.//AbstractText')])
        journal=art.findtext('.//Journal/Title','')
        pubdate=art.findtext('.//PubDate/Year','')
        authors=[f"{a.findtext('ForeName')} {a.findtext('LastName')}".strip() for a in art.findall('.//Author') if a.findtext('LastName') and a.findtext('ForeName')]
        return {'pmid':pmid,'title':title,'abstract':abstract,'authors':authors,'journal':journal,'publication_date':pubdate}
    except Exception as e:
        return {'error':str(e),'pmid':pmid}

def search_pubmed_by_title_authors(title, authors=None):
    url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
    q=f'"{title}"[Title]'
    if authors:
        q+=' ' + ' '.join([f"{a.split()[-1]}[Author]" for a in authors])
    try:
        r=requests.get(url, params={'db':'pubmed','term':q,'retmode':'json','retmax':1}, timeout=DEFAULT_TIMEOUT); r.raise_for_status()
        ids=r.json().get('esearchresult',{}).get('idlist',[])
        return ids[0] if ids else None
    except Exception:
        return None

def search_pmc(title):
    url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
    try:
        r=requests.get(url, params={'db':'pmc','term':title,'retmode':'json','retmax':5}, timeout=DEFAULT_TIMEOUT); r.raise_for_status()
        ids=r.json().get('esearchresult',{}).get('idlist',[])
        return ids
    except Exception:
        return []

def fetch_pmc_esummary(pmcid):
    url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi'
    try:
        r=requests.get(url, params={'db':'pmc','id':pmcid,'retmode':'json'}, timeout=DEFAULT_TIMEOUT); r.raise_for_status()
        return r.json()
    except Exception:
        return {'error':'pmc esummary failed','pmcid':pmcid}

def convert_pmc_summary_to_metadata(esum):
    res=esum.get('result',{}); out={}
    for uid in res.get('uids',[]):
        rec=res.get(uid,{})
        out[uid]={'title':rec.get('title'),'pubdate':rec.get('pubdate'),'authors':rec.get('authors'),'doi':rec.get('articleids',{}),'pmid':rec.get('pmid')}
    return out

def fetch_clinical_trial_and_pubmed_pmc(nct):
    clin=fetch_clinical_trial_data(nct)
    if 'error' in clin: return clin
    ct=clin.get('clinical_trial_data',{})
    protocol=ct.get('protocolSection',{}) if isinstance(ct,dict) else {}
    refs=protocol.get('referencesModule',{}).get('referenceList',[]) if protocol else []
    if not refs:
        title=(protocol.get('identificationModule',{}).get('officialTitle') or protocol.get('identificationModule',{}).get('briefTitle')) if protocol else ''
        officials=protocol.get('contactsLocationsModule',{}).get('overallOfficials',[]) if protocol else []
        authors=[o.get('name') for o in officials if 'name' in o]
        if title: refs=[{'title':title,'authors':authors}]
    pubmed={'pmids':[],'studies':[]}
    pmc={'pmcids':[],'summaries':[]}
    for ref in refs:
        title=ref.get('referenceTitle') or ref.get('title')
        authors=ref.get('authors',[])
        pmid=search_pubmed_by_title_authors(title, authors)
        if pmid:
            pubmed['pmids'].append(pmid)
            pubmed['studies'].append(fetch_pubmed_by_pmid(pmid))
        pmcids=search_pmc(title)
        for pid in pmcids:
            if pid not in pmc['pmcids']:
                pmc['pmcids'].append(pid)
                pmc['summaries'].append({'pmcid':pid,'metadata':convert_pmc_summary_to_metadata(fetch_pmc_esummary(pid))})
    return {'nct_id':nct,'sources':{'clinical_trials':{'source':clin.get('source'),'data':ct},'pubmed':pubmed,'pmc':pmc}}

def print_study_summary(result):
    protocol=result['sources']['clinical_trials']['data'].get('protocolSection',{})
    ident=protocol.get('identificationModule',{})
    print("===== STUDY =====")
    print(ident.get('officialTitle',ident.get('briefTitle','Untitled')))
    print("Status:", protocol.get('statusModule',{}).get('overallStatus'))
    pubs=result['sources']['pubmed']['studies']
    if pubs:
        print("PUBMED:")
        for p in pubs:
            print(p.get('title'), p.get('publication_date'), p.get('pmid'))
    pmcids=result['sources']['pmc']['pmcids']
    if pmcids:
        print("PMC:", ', '.join(pmcids))

def summarize_result(result):
    pmids=result.get('sources',{}).get('pubmed',{}).get('pmids',[])
    pmcids=result.get('sources',{}).get('pmc',{}).get('pmcids',[])
    return {'NCT': result.get('nct_id'),'ClinicalTrials.gov Source': result.get('sources',{}).get('clinical_trials',{}).get('source'),'PubMed Count': len(pmids),'PMC Count': len(pmcids),'PubMed IDs': ', '.join(pmids) if pmids else 'None','PMC IDs': ', '.join(pmcids) if pmcids else 'None'}

def save_results(results, filename, fmt='txt'):
    Path('output').mkdir(exist_ok=True)
    if fmt=='csv':
        import csv
        path=f'output/{filename}.csv'
        keys=['NCT','ClinicalTrials.gov Source','PubMed Count','PMC Count','PubMed IDs','PMC IDs']
        with open(path,'w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for r in results:
                writer.writerow(summarize_result(r))
    else:
        path=f'output/{filename}.txt'
        with open(path,'w',encoding='utf-8') as f:
            for r in results:
                f.write(json.dumps(r,indent=2))
                f.write('\n\n')
    print(f"Saved to {path}")
