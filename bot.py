import slack
import os
import pathlib
import subprocess
import requests
from pathlib import Path
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack.errors import SlackApiError
from script_for_bot import *
from panacea_2_script import *

env_path = Path('/home/nutanix/slackbot-bot2/.env')
load_dotenv(dotenv_path=env_path)
slack_bot_token=os.environ['SLACK_TOKEN']
slack_app_token=os.environ['SLACK_APP_TOKEN']
app = App(token=slack_bot_token)


# client=slack.WebClient(token=os.environ['SLACK_TOKEN'])
# client.chat_postMessage(channel='C081J3M4LAX',text="kiven")

def remove_URL(sample):
    if '|' in sample:
        return sample.split('|')[-1].rstrip('>')
    else :
        return sample

def remove_ip_from_url(url):
    # Regular expression to match protocol and IP (with optional port)
    return re.sub(r'^(https?://)?(\d{1,3}\.){3}\d{1,3}(:\d+)?/', '', url)

@app.message("hello")
def message_hello(message, say):
    # say() sends a message to the channel where the event was triggered
    say(f"Hey there <@{message['user']}>!") 


@app.event("message")
def handle_message_events(body,event, say,client):

    channel_id = event['channel']
    thread_ts = event.get('thread_ts')
    try:
        # Retrieve the most recent message in the channel
        if thread_ts:
            # If the message is part of a thread, fetch the latest message in the thread
            result = client.conversations_replies(channel=channel_id, ts=thread_ts, limit=1, inclusive=False)
            latest_message = result['messages'][-1]  # Get the last message in the replies (latest)
            # print("1 latest message->",latest_message.get("text", ""),"\n")
        else:
            # If not a thread, fetch the latest message in the main conversation
            result = client.conversations_history(channel=channel_id, limit=1)
            latest_message = result['messages'][0]
            # print("2 latest message->",latest_message.get("text", ""),"\n")
        # print("latest message->",latest_message.get("text", ""),"\n")
        # print("event message -->", event.get("text", ""),"\n")
        if latest_message['ts'] == event['ts']:
            event = body.get("event", {})
            text = event.get("text", "")
            user = event.get("user", "")
            channel = event.get("channel", "")
            ts = event.get("ts", "")
            # print(f"Raw message -> {text}")
            # msg=remove_URL(text)
            print(f"Message received from user {user} in channel {channel}: {text}")
            ans=[]
            ans=start(text)
            if ans == None:
                say(f"No Failure Found. ", thread_ts=ts)
                return
            global_flag=ans[0]
            global_link=ans[1]
            # print("global_link __@ = ",global_link)

            if global_flag == 1:
                say(f"Deployment Failure Found. Log Links :{global_link} ", thread_ts=ts)
                url_1=remove_ip_from_url(global_link)
                say(url_1,thread_ts=ts)
                panacea_main('rdm',url_1,say,ts)
            elif global_flag == 2:
                say(f"Nutest Failure Found. Log Links :{global_link} ", thread_ts=ts)
                url_1=remove_ip_from_url(global_link)
                panacea_main('jita_tester_precommit_afs',url_1,say,ts)
                # say(f"Output is ```\n{output}\n```", thread_ts=ts)
            else:
                say(f"No Failure Found. ", thread_ts=ts)
     
            
    except SlackApiError as e:
        print(f"Error fetching conversation history: {e.response['error']}")
        return
    

if __name__ == "__main__":
    handler = SocketModeHandler(app, slack_app_token)
    handler.start()
    app.run(debug=True)
