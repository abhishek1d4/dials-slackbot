import threading
import requests
import concurrent.futures
import time
import urllib.parse
import warnings
from urllib3.exceptions import InsecureRequestWarning
from functools import partial

PROD_URL = "10.113.24.26"
# for prod : use https:/10.113.24.26/
DEV_URL = "10.113.24.33:1999"

host=DEV_URL

METADATA_URL = f'http://{host}/api/load-balancer/logs/metadata'
ANALYZE_URL = f'http://{host}/api/load-balancer/logs/analyze'
JOB_STATUS_URL = f'http://{host}/api/load-balancer/logs/job_status'
SUMMARY_URL=f'http://10.113.24.33:1998/api/components_issues' # todo : add headers in this 
REPORT_URL=f'http://10.113.24.33/dashboard'
POLL_TIMEOUT = 20 * 60
USER_EMAIL = "abhishek.bisla@nutanix.com"


warnings.simplefilter('ignore', InsecureRequestWarning)
def format_finding(finding):
    formatted = ""
    if 'problem' in finding:
        formatted += f"*Problem:* {finding['problem']}\n"
    else:
        formatted += "*Problem:* N/A\n"

    if 'cause' in finding:
        formatted += f"*Cause:* {finding['cause']}\n"
    else:
        formatted += "*Cause:* N/A\n"

    if 'impact' in finding:
        formatted += f"*Impact:* {finding['impact']}\n"
    else:
        formatted += "*Impact:* N/A\n"

    if 'remediation' in finding:
        formatted += f"*Remediation:* {finding['remediation']}"
    else:
        formatted += "*Remediation:* N/A\n"

    if 'severity' in finding:
        formatted += f"*Severity:* {finding['severity']}\n"
    else:
        formatted += "*Severity:* N/A\n"
    formatted += "-----------------------------"
    return formatted

def split(bundle):
    parts = bundle.split('/')

# Get the last element, or the second-last if the last is empty
     last_variable = parts[-1] if parts[-1] else parts[-2]
    return parts 
def result_summary(bundle, log_bundle_id, say, ts):
    headers = {
    "log_bundle_id": log_bundle_id  # Add the log_bundle_id header
    }
    summary_url = f"{SUMMARY_URL}?log_bundle_id={log_bundle_id}&component_name=&issue_provider=panacea_findings"
    try:
        summary_response = requests.get(summary_url,headers=headers, verify=False)
        summary_response.raise_for_status()
        summary_response = summary_response.json()
        panacea_findings = summary_response.get("panacea_findings", [])

        if len(panacea_findings) == 0:
            say(f"No match found for `{bundle.split('/')[-1]}`\n", thread_ts=ts)
        else:
            findings_text = "\n\n".join(format_finding(finding) for finding in panacea_findings)
            say(f"\n`Match for {bundle.split('/')[-1]}:`\n\n{findings_text}", thread_ts=ts)

    except requests.RequestException as e:
        say(f"Failed to fetch summary for `{bundle.split('/')[-1]}`. Error: {str(e)}", thread_ts=ts)
      

def analyze_logs(entry,say,ts):
    # thread_name = threading.current_thread().name
    log_type=entry["log_type"]
    payload = {
        "log_bundle_path": entry["remote_log_bundle_path"],
        "sfdc_case_no": entry["sfdc_case_no"],
        "user_email": USER_EMAIL,
        "log_type": log_type,
    }
    
    try:
        analyze_response = requests.post(ANALYZE_URL, json=payload, verify=False)
        analyze_response.raise_for_status()
        analyze_response=analyze_response.json()
        time.sleep(15)
        if analyze_response.get("status")=="failure" and analyze_response.get("error_msg")!="Log bundle already exists":
            say(f'Log analysis for {entry["remote_log_bundle_path"].split("/")[-1]} failed with error: {analyze_response.get("error_msg")}',thread_ts=ts)
            return
        
        log_bundle_path_encoded = urllib.parse.quote(entry["remote_log_bundle_path"])
        log_bundle_id=analyze_response.get("log_bundle_id")
        poll_url = f"{JOB_STATUS_URL}?log_bundle_path={log_bundle_path_encoded}&log_type={log_type}"
        
        start_time = time.time()

        while True:
            if time.time() - start_time > POLL_TIMEOUT:
                print(f"Timeout reached for {entry['cluster_uuid'].split('/')[-1]} after 20 minutes.")
                say(f"Timeout reached for {entry['cluster_uuid'].split('/')[-1]} after 20 minutes." ,thread_ts=ts)
                break

            poll_response = requests.get(poll_url, verify=False)
            poll_response.raise_for_status()
            poll_response=poll_response.json()
            
            if poll_response.get("job_status") == "completed":
                result_summary(entry['remote_log_bundle_path'],log_bundle_id,say,ts)
                report_url=REPORT_URL+f'?log_bundle_id={log_bundle_id}'
                print(f'Report url for {entry["remote_log_bundle_path"].split("/")[-1]} is ',report_url)
                say(f'`Report url for {entry["remote_log_bundle_path"].split("/")[-1]}:`{report_url} \n', thread_ts=ts)
                break
            elif poll_response.get("job_status") == "waiting":
                say('Polling',thread_ts=ts) 
                time.sleep(20)

    except Exception as e:
        say(f"An error occurred: {e}" ,thread_ts=ts)


def panacea_main(log_type,log_bundle_path,say,ts): 
    
    metadata_data = {
        'log_bundle_path': log_bundle_path,
        'sfdc_case_no': '',
        'log_type': log_type
    }
    say(f"Panacea analysis started" ,thread_ts=ts)

    
    try:
        metadata_response = requests.post(METADATA_URL, json=metadata_data, verify=False)
        metadata_response.raise_for_status()
        metadata_response=metadata_response.json()
       
        if metadata_response.get("status") !="success":
            msg=metadata_response.get["message"]
            say(f"Metadata api respose failed with:```\n{msg}\n```", thread_ts=ts)
            return
        
        paths = metadata_response.get("metadata_records", [])
        if(len(paths)==0):
            say(f"No log bundles paths found", thread_ts=ts)
            return
        
        say(f"Below {len(paths)} log bundles have been identified:",thread_ts=ts)
       
        for path in paths:
            say(f"`{path.get('remote_log_bundle_path')}`\n",thread_ts=ts)
        
        analyze_logs_with_args = partial(analyze_logs, say=say, ts=ts)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:  
            executor.map(analyze_logs_with_args, paths)
        
        say(f"Panacea execution completed", thread_ts=ts)
        
    except Exception as e:
        say(f"Error occured is ```\n{e}\n```", thread_ts=ts)
