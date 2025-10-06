# Copy your synchronous implementation into this module.
# For brevity, include a minimal working example that hits ClinicalTrials and PubMed.
import requests, time, xml.etree.ElementTree as ET, json
DEFAULT_TIMEOUT=15; SLEEP_BETWEEN_REQUESTS=0.34; CTG_V2_BASE='https://clinicaltrials.gov/api/v2/studies'; CTG_LEGACY_FULL='https://clinicaltrials.gov/api/query/full_studies'
def fetch_clinical_trial_data(nct_id):
    nct = nct_id.strip().upper(); url=f'{CTG_V2_BASE}/{nct}'; print(f'🔍 ClinicalTrials.gov v2: fetching {url}')
    try:
        r=requests.get(url,timeout=DEFAULT_TIMEOUT); 
        if r.status_code==200: return {'nct_id':nct,'clinical_trial_data':r.json(),'source':'clinicaltrials_v2_detail'}
        if r.status_code==404: print('⚠️ v2 detail 404'); 
    except Exception as e: print('❌ CTG v2 detail failed',e)
    # fallback legacy
    try:
        params={'expr':nct,'min_rnk':1,'max_rnk':1,'fmt':'json'}; r=requests.get(CTG_LEGACY_FULL,params=params,timeout=DEFAULT_TIMEOUT); r.raise_for_status(); data=r.json()
        studies=data.get('FullStudiesResponse',{}).get('FullStudies',[])
        if studies: return {'nct_id':nct,'clinical_trial_data':studies[0].get('Study',{}),'source':'clinicaltrials_legacy_full'}
    except Exception as e: print('❌ CTG legacy failed',e)
    return {'error':f'No study found for {nct}','source':'clinicaltrials_not_found'}

def fetch_pubmed_by_pmid(pmid):
    url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi'; params={'db':'pubmed','id':pmid,'retmode':'xml'}
    try:
        r=requests.get(url,params=params,timeout=DEFAULT_TIMEOUT); r.raise_for_status(); root=ET.fromstring(r.text)
    except Exception as e: return {'error':str(e),'source':'pubmed_api','pmid':pmid}
    art=root.find('.//PubmedArticle'); 
    if art is None: return {'error':'No article found','source':'pubmed_api','pmid':pmid}
    title=art.findtext('.//ArticleTitle',''); abstract=''.join([t.text or '' for t in art.findall('.//AbstractText')])
    journal=art.findtext('.//Journal/Title',''); pub_date=art.findtext('.//PubDate/Year',''); authors=[f\"{a.findtext('ForeName')} {a.findtext('LastName')}\".strip() for a in art.findall('.//Author') if a.findtext('LastName') and a.findtext('ForeName')]
    return {'pmid':pmid,'title':title,'abstract':abstract,'authors':authors,'journal':journal,'publication_date':pub_date,'url':f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/','source':'pubmed_api'}

def search_pubmed_by_title_authors(title, authors=None):
    from urllib.parse import quote; q=f'\"{title}\"[Title]'; 
    if authors: q += ' AND ' + ' AND '.join([f\"{a.split()[-1]}[Author]\" for a in authors if a.strip()])
    url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'; params={'db':'pubmed','term':q,'retmode':'json','retmax':1}
    try: r=requests.get(url,params=params,timeout=DEFAULT_TIMEOUT); r.raise_for_status(); time.sleep(SLEEP_BETWEEN_REQUESTS); ids=r.json().get('esearchresult',{}).get('idlist',[]); return ids[0] if ids else None
    except Exception as e: return None

def search_pmc(title):
    url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'; params={'db':'pmc','term':title,'retmode':'json','retmax':5}
    try: r=requests.get(url,params=params,timeout=DEFAULT_TIMEOUT); r.raise_for_status(); time.sleep(SLEEP_BETWEEN_REQUESTS); return r.json().get('esearchresult',{}).get('idlist',[])
    except Exception as e: return []

def fetch_pmc_esummary(pmcid):
    url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi'; params={'db':'pmc','id':pmcid,'retmode':'json'}
    try: r=requests.get(url,params=params,timeout=DEFAULT_TIMEOUT); r.raise_for_status(); time.sleep(SLEEP_BETWEEN_REQUESTS); return r.json()
    except Exception as e: return {'error':str(e)}

def convert_pmc_summary_to_metadata(esum):
    res=esum.get('result',{}); out={}
    for uid in res.get('uids',[]): rec=res.get(uid,{}); out[uid]={'title':rec.get('title'),'pubdate':rec.get('pubdate'),'authors':rec.get('authors'),'doi':rec.get('articleids',{}),'pmid':rec.get('pmid')}
    return out

def fetch_clinical_trial_and_pubmed_pmc(nct_id):
    clin=fetch_clinical_trial_data(nct_id)
    if 'error' in clin: return clin
    ctdata=clin.get('clinical_trial_data',{}); protocol=ctdata.get('protocolSection',{}) if isinstance(ctdata,dict) else {}
    refs=protocol.get('referencesModule',{}).get('referenceList',[])
    if not refs:
        title=(protocol.get('identificationModule',{}).get('officialTitle') or protocol.get('identificationModule',{}).get('briefTitle'))
        officials=protocol.get('contactsLocationsModule',{}).get('overallOfficials',[]); authors=[o.get('name') for o in officials if 'name' in o]
        if title: refs=[{'title':title,'authors':authors}]
    pubmed={'pmids':[],'studies':[],'search_methods':[]}; pmc={'pmcids':[],'summaries':[],'search_methods':[]}
    for ref in refs:
        pmid,method=None,'no_match'
        # try direct ids
        if ref.get('pmid'): pmid,method=ref.get('pmid'),'pmid_direct'
        if not pmid and ref.get('doi'): 
            pm = search_pubmed_by_title_authors(ref.get('doi'),None); 
            if pm: pmid,method=pm,'doi_to_pmid'
        if not pmid and ref.get('pmcid'): 
            # convert via elink
            pass
        if not pmid:
            title = ref.get('referenceTitle') or ref.get('title'); authors=ref.get('authors',[])
            if title:
                found = search_pubmed_by_title_authors(title, authors)
                if found: pmid,method=found,'title_author'
        pubmed['search_methods'].append(method)
        if pmid and pmid not in pubmed['pmids']:
            pubmed['pmids'].append(pmid); pubmed['studies'].append(fetch_pubmed_by_pmid(pmid))
        pmcids = search_pmc(ref.get('referenceTitle') or ref.get('title') or '')
        for pid in pmcids:
            if pid not in pmc['pmcids']:
                pmc['pmcids'].append(pid); pmc['summaries'].append({'pmcid':pid,'metadata':convert_pmc_summary_to_metadata(fetch_pmc_esummary(pid))})
    return {'nct_id':nct_id,'sources':{'clinical_trials':{'source':clin.get('source'),'data':ctdata},'pubmed':pubmed,'pmc':pmc}}
