# Place your existing synchronous data_fetchers here.
# For the package, we include stubs pointing to your existing implementations.
from . import data_fetchers_impl as impl
fetch_clinical_trial_data = impl.fetch_clinical_trial_data
fetch_clinical_trial_and_pubmed_pmc = impl.fetch_clinical_trial_and_pubmed_pmc
fetch_pubmed_by_pmid = impl.fetch_pubmed_by_pmid
summarize_result = impl.summarize_result
print_study_summary = impl.print_study_summary
save_results = impl.save_results
