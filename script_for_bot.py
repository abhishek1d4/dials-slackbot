import requests
from dotenv import load_dotenv
import os
import pathlib
from pathlib import Path
import re
import json
# Function to get ticket details from JIRA
global_flag=0
global_link=""
env_path = Path('/home/nutanix/slackbot-bot2/.env')
load_dotenv(dotenv_path=env_path)
jira_token=os.environ['JIRA_TOKEN']
jira_base_url = "https://jira.nutanix.com"
rdm_base_url = "https://rdm.eng.nutanix.com/"
jita_base_url="https://jita.eng.nutanix.com/"


def get_jira_ticket_details(ticket_id, jira_base_url, jira_token):
    jira_url = f"{jira_base_url}/browse/{ticket_id}"
    api_url = f"{jira_base_url}/rest/api/2/issue/{ticket_id}"
    headers = {
        "Authorization": f"Bearer {jira_token}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error accessing JIRA API: {e}")
        return None

def find_link(ticket_data,base_url):
    if not ticket_data:
        return None
    
    fields = ticket_data.get("fields", {})
    description = fields.get("description", "")

    
    if base_url in description:
        start_index = description.find(base_url)
        next_space = description.find(" ", start_index)
        next_https = description.find("https://", start_index + len(base_url))
        next_http = description.find("http://", start_index + len(base_url))
        # Determine the end of the link via next https or space or end of description ends the link
        possible_ends = [next_space, next_https,next_http, len(description),]
        end_index = min([index for index in possible_ends if index != -1])
        return description[start_index:end_index]
    
    return None

# Function to extract unique identifier from JITA link
def extract_unique_id(jita_link):
    match = re.search(r"/reports/([a-zA-Z0-9]+)", jita_link)
    return match.group(1) if match else None

# Function to hit the JITA API and extract all $oid values
def get_oid_values(unique_id, jita_api_base_url):
    api_url = f"{jita_api_base_url}/api/v2/jobs/{unique_id}"
    try:
        headers = {
            'Content-Type': 'application/json'
        }
        response = requests.get(api_url,verify=False, timeout=30)
        response.raise_for_status()
        data = response.json()
        oids = [
            task["id"]["$oid"]
            for task in data.get("data", {}).get("tasks", [])
            if "id" in task and "$oid" in task["id"]
        ]
        return oids
    except requests.exceptions.RequestException as e:
        print(f"Error accessing JITA API: {e}")
        return []

def get_failed_provision_request_ids(oids, jita_api_base_url):
    failed_provision_request_ids = []
    
    for oid in oids:
        query = {
            "task_id": {"$in": [{"$oid": oid}]}
        }
        api_url = f"{jita_api_base_url}/api/v2/deployments?paginate=false&raw_query={json.dumps(query)}"
        try:
            response = requests.get(api_url,verify=False, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            for deployment in data.get("data", []):
                if deployment.get("status") == "failed":
                    provision_request_id = deployment.get("provision_request_id", {}).get("$oid")
                    if provision_request_id:
                        failed_provision_request_ids.append(provision_request_id)
        except requests.exceptions.RequestException as e:
            print(f"Error accessing deployments API for $oid {oid}: {e}")

    return failed_provision_request_ids


def get_log_link(provision_request_id, rdm_api_base_url):
    api_url = f"{rdm_api_base_url}api/v1/scheduled_deployments/{provision_request_id}"
    try:
        # Hit the API and parse the response
        response = requests.get(api_url, verify=False, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        scheduled_data = data.get("data", {})
        
        # Check for deployments in the response
        deployments = scheduled_data.get("deployments", [])
        if not deployments:
            print(f"No deployments found for provision_request_id {provision_request_id}.")
            return None

        # Iterate through deployments to find the failed one
        for deployment in deployments:
            deployment_oid = deployment.get("$oid")
            deployment_details_url = f"{rdm_api_base_url}api/v1/deployments/{deployment_oid}"
            
            # Fetch deployment details
            deployment_details_response = requests.get(deployment_details_url, verify=False, timeout=30)
            deployment_details_response.raise_for_status()
            
            # Parse deployment details
            deployment_data = deployment_details_response.json().get("data", {})
            if deployment_data.get("status") == "FAILED":
                print(f"Failed deployment found: {deployment_oid}")
                return deployment_data.get("log_link")
        
        print("No failed deployments found.")
        return None

    except requests.exceptions.RequestException as e:
        print(f"Error accessing RDM API for provision_request_id {provision_request_id}: {e}")
        return None

def find_deployment_links(failed_provision_request_id):

    log_link = get_log_link(failed_provision_request_id, rdm_base_url)
    if log_link:
        print(f"Log link for provision_request_id {failed_provision_request_id}: {log_link}")
        global global_flag
        global global_link
        global_flag=1
        global_link=log_link
        return 1
    else:
        print(f"Log link not found for provision_request_id {failed_provision_request_id}")
        return 0


def check_deployment_failure(jita_link):
    unique_id = extract_unique_id(jita_link)
    if not unique_id:
        print("Failed to extract unique ID from JITA link.")
        return 0
    print(f"Unique ID extracted: {unique_id}")

    oids = get_oid_values(unique_id, jita_base_url)
    if oids:
        print("Extracted $oid values:")
        for oid in oids:
            print(f"- {oid}")
    else:
        print("No $oid values found.")
        return 0

    failed_provision_request_ids = get_failed_provision_request_ids(oids, jita_base_url)
    if failed_provision_request_ids:
        print("Failed provision_request_ids:")
        for provision_id in failed_provision_request_ids:
            print(f"- {provision_id}")
    else:
        print("No failed provision_request_ids found.")
        return 0
    #Only executing on 1st failure
    return find_deployment_links(failed_provision_request_ids[0])
  

def find_nutest_url(oid):
    # query = {"status":"Failed", "agave_task_id":{"$in":[{"$oid":oid}]}}
    # print("oid----->",oid)
    query = {
            "status": "Failed",
            "agave_task_id": {"$in": [{"$oid": oid}]}
        }
    api_url = f"{jita_base_url}/api/v2/test_results?paginate=false&raw_query={json.dumps(query)}"
    try:
        # Make the API call to fetch test results
        response = requests.get(api_url, verify=False, timeout=30)
        response.raise_for_status()
        response_data = response.json()
        
        # Parse response for test_log_url and test details
        test_data = response_data.get("data", [])
        if not test_data:
            print(f"No failed tests found for oid {oid}.")
            return None
        
        # Assume we take the first failed test
        test_result = test_data[0]
        test_log_url = test_result.get("test_log_url")
        print("Nutest Page url--->",test_log_url)
        test_name_path = test_result.get("test", {}).get("name", "").replace('.', '/')
        print("test_name_path--->",test_name_path)
        try:
            r=requests.get(test_log_url,verify=False, timeout=30)
            print("Redirected URL->",r.url)
            final_test_url=r.url+"/"+test_name_path
            print("final_test_url-->",final_test_url)
            return final_test_url
        except requests.exceptions.RequestException as e:
            print(f"Error finding the redirection of Nutest URL: {e}")
            return None


    except requests.exceptions.RequestException as e:
        print(f"Error accessing Jita API for oid {oid}: {e}")
        return None
                
def check_nutest_failure(jita_link):
    unique_id = extract_unique_id(jita_link)
    if not unique_id:
        print("Failed to extract unique ID from JITA link.")
        return 0
    print(f"Unique ID extracted: {unique_id}")

    oids = get_oid_values(unique_id, jita_base_url)
    if oids:
        print("Extracted $oid values:")
        for oid in oids:
            print(f"- {oid}")
    else:
        print("No $oid values found.")
        return 0
    if len(oids) != 1 :
        print("More than one $oid values found.Only First will be analysed")
    
    url=find_nutest_url(oids[0])
    if( url == None or url==0 or len(url)==0):
        print(f"Log link not found")
        return 0

    print(f"Log link is:",url)
    global global_flag
    global global_link
    global_flag=2
    global_link=url
    return 1

def extract_provisional_id(url):
    # Define the regular expression pattern to extract the provisional ID
    pattern = r"/scheduled_deployments/([a-f0-9]{24})"
    
    # Search for the pattern in the URL
    match = re.search(pattern, url)
    
    # Return the captured group (provisional ID) if found
    return match.group(1) if match else None

def dial_handle(ticket_id):
    print("ticket id = ",ticket_id)
    ticket_data = get_jira_ticket_details(ticket_id, jira_base_url, jira_token)
    if not ticket_data:
        print("Failed to retrieve ticket details.")
        return
    
    jita_link=find_link(ticket_data,jita_base_url)
    rdm_link = find_link(ticket_data,rdm_base_url)
    flag=0
    if jita_link:
        print(f"JITA Link found: {jita_link}")
        flag=check_deployment_failure(jita_link)
        if flag==0:
            print(f"------------->>>>>>>>> No DEPLOYMENT FAILURE DETECTED <<<<<<<<<<-------------")
            print(f"Find in Nuntest Logs Location")
            flag=check_nutest_failure(jita_link)

    else:
        print("JITA Link not found in the ticket.")
        print(f"JITA Link not found.Therefore assuming deployment failure only.Finding Logs Location for RDM scheduled deployments")
        if rdm_link:
            print(f"RDM Link found: {rdm_link}")
            provisional_id=extract_provisional_id(rdm_link)
            if provisional_id :
                find_deployment_links(provisional_id)
            else :
                print("Unable to process link")
            # check_deployment_failure from RDM LINKS ???
        else:
            print("RDM Link not found in the ticket.")
            print(f"No JITA and RDM Links found.Ending Script!")


def start(user_input):
    global global_flag
    global global_link
    global_flag=0
    global_link=""
    # accepted_inputs = {
    # "DIAL_ID": r"(?i)DIAL-\d+",  # e.g., DIAL-16565
    # "RDM_URL": r"https://rdm\.eng\.nutanix\.com/scheduled_deployments/([a-f0-9]{24})",  # e.g., RDM link
    # "JITA_URL": r"https://jita\.eng\.nutanix\.com/nucloud/reports/([a-f0-9]{24})",  # e.g., JITA link
    # }
    rdm_url_pattern = re.compile(r"https://rdm\.eng\.nutanix\.com/scheduled_deployments/[\w-]+")
    dial_name_pattern=re.compile(r"(?i)DIAL-\d+")
    jita_url_pattern=re.compile(r"https://jita\.eng\.nutanix\.com/nucloud/reports/[\w-]+")

    jita_1=jita_url_pattern.findall(user_input)
    dial_1=dial_name_pattern.findall(user_input)
    rdm_1=rdm_url_pattern.findall(user_input)

    if len(jita_1) != 0:
        # print("jita 1 -->",jita_1[0])
        flag=0
        print(f"JITA Link found: ",jita_1)
        flag=check_deployment_failure(jita_1[0])
        if flag==0:
            print(f"------------->>>>>>>>> No DEPLOYMENT FAILURE DETECTED <<<<<<<<<<-------------")
            print(f"Find in Nuntest Logs Location")
            flag=check_nutest_failure(jita_1[0])
        if flag==0:
            print("Logs not found")
    elif len(dial_1)!=0 :
        print(f"Processing DIAL ID: {dial_1}")
        dial_handle(dial_1[0])
    elif len(rdm_1)!=0:
        provisional_id=extract_provisional_id(rdm_1[0])
        if provisional_id :
            print("provisional id-->",provisional_id)
            find_deployment_links(provisional_id)
        else :
            print("Unable to process link")

    else:
        print( "Unhandled input type.")

    # print("global_flag -> = ",global_flag)
    # print("global_link -> = ",global_link)
    ans=[]
    ans.append(global_flag)
    ans.append(global_link)
    return ans



