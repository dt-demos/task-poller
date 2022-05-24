#Import the flask module
from syslog import LOG_INFO
from flask import Flask, request, make_response,render_template
import json
import os
import xml.etree.ElementTree as ET
import requests
from requests.structures import CaseInsensitiveDict
import random
from datetime import datetime
import sqlite3
from sqlite3 import Error

app = Flask(__name__)

# some constants
LOADRUNNER_FINISHED_STATUS="Finished"
LOADRUNNER_RUNNING_STATUS="Running"
TASK_STATUS_STARTED="started"
TASK_STATUS_DONE="done"
LOG_DIR="logs"
APP_LOGNAME=os.path.join(LOG_DIR,"app.log")
REQUEST_LOGNAME=os.path.join(LOG_DIR,"request.log")
KEPTN_API_LOGNAME=os.path.join(LOG_DIR,"keptn_api_call.log")
DATABASE_FILENAME="taskpoller.db"
SECRETS_FILE="secrets.json"
LOGINFO="INFO"
LOGERROR="ERROR"
LOGDEBUG="DEBUG"

# some globals
conn=None
KEPTN_BASE_URL=""
KEPTN_API_TOKEN=""
LOADRUNNER_BASEURL=""
LOADRUNNER_API_TOKEN=""
LOGLEVEL=LOGINFO

############################################################
# GENERAL FUNCTIONS
############################################################

def log(loglevel,logtext):
    global APP_LOGNAME
    printlog=False
    if LOGLEVEL==LOGDEBUG:
        printlog=True
    if (LOGLEVEL==LOGINFO) and (loglevel==LOGINFO):
        printlog=True
    if (LOGLEVEL==LOGERROR) and (loglevel==LOGERROR):
        printlog=True

    if printlog:
        print(logtext)
        f = open(APP_LOGNAME, "a")
        f.write(logtext + "\n")
        f.close()

def add_request_log(logtext):
    global REQUEST_LOGNAME
    dt = datetime.now()
    f = open(REQUEST_LOGNAME, "a")
    f.write("Date and Time  : " + str(dt) + "\n")
    f.write(logtext + "\n")
    f.close()

def resetlogs():
    global REQUEST_LOGNAME
    global KEPTN_API_LOGNAME
    global APP_LOGNAME
    f = open(REQUEST_LOGNAME, "w")
    f.write("")
    f.close()
    f = open(KEPTN_API_LOGNAME, "w")
    f.write("")
    f.close()
    f = open(APP_LOGNAME, "w")
    f.write("")
    f.close()
    return "Reset Logs complete"

# abort it there are no credentials as env. variables
def get_secrets():
    global KEPTN_BASE_URL
    global KEPTN_API_TOKEN
    global LOADRUNNER_BASEURL
    global LOADRUNNER_API_TOKEN
    global SECRETS_FILE
    global LOGINFO
    global LOGDEBUG
    global LOGERROR
    
    log(LOGINFO,"Load secrets from file: " + SECRETS_FILE)

    with open(SECRETS_FILE, "r") as secrets_file:
        secrets = json.load(secrets_file)
        KEPTN_BASE_URL = secrets["KEPTN_BASE_URL"]
        KEPTN_API_TOKEN = secrets["KEPTN_API_TOKEN"]
        LOADRUNNER_BASEURL = secrets["LOADRUNNER_BASEURL"]
        LOADRUNNER_API_TOKEN = secrets["LOADRUNNER_API_TOKEN"]

    log(LOGDEBUG,"------------------------------------------------")
    log(LOGDEBUG,"Secrets")
    log(LOGDEBUG,"------------------------------------------------")
    log(LOGDEBUG,"KEPTN_BASE_URL       = " + KEPTN_BASE_URL)
    log(LOGDEBUG,"KEPTN_API_TOKEN      = " + KEPTN_API_TOKEN)
    log(LOGDEBUG,"LOADRUNNER_BASEURL   = " + LOADRUNNER_BASEURL)
    log(LOGDEBUG,"LOADRUNNER_API_TOKEN = " + LOADRUNNER_API_TOKEN)
    log(LOGDEBUG,"------------------------------------------------")

############################################################
# DATABASE FUNCTIONS
############################################################

def create_connection(db_file):
    global LOGERROR
    try:
        conn = sqlite3.connect(db_file, check_same_thread=False)
        return conn
    except Error as e:
        log(LOGERROR,e)
    return conn

def update_database_task(runid,status):
    global LOGINFO
    global LOGDEBUG
    global LOGERROR
    global conn
    sql = "UPDATE task "
    sql+= "SET status='" + status + "' "
    sql+= "WHERE runid = '" + runid + "'"

    log(LOGDEBUG,"update_database_task: Updating task sql = " + sql)
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()
    log(LOGINFO,"update_database_task: Updated runid = " + runid + " to status = " + status)

############################################################
# PROCESSING LOGIC FUNCTIONS
############################################################

def process_loadrunner_task(task):
    global LOGINFO
    global LOGDEBUG
    global LOGERROR

    #######################################
    # Step 1 - call test tool to get status
    #######################################
    global LOADRUNNER_BASEURL

    # this is a simulated call that wll return the XML of the LoadRunner API
    #https://admhelp.microfocus.com/lre/en/all/api_refs/Performance_Center_REST_API/Content/Get_Run_Status.htm
    # this would be replaced with a real call to loadrunner
    url = LOADRUNNER_BASEURL + "/simulate_loadrunner_runstatus"
    log(LOGINFO,"process_loadrunner_task: Calling = " + url)
    headers = CaseInsensitiveDict()
    headers["Accept"] = "application/xml"
    response = requests.get(url,headers=headers)
    
    # this a logic to parse the resulting XML response for the RunState element
    try:
        root = ET.fromstring(response.content)
        log(LOGINFO,"process_loadrunner_task: Got XML Response")
    except Error as e:
        log(LOGERROR,"process_loadrunner_task: Error processing response content. Got: " + response.content)
        return 
    
    try:
        runstate=root.find('{http://www.hp.com/PC/REST/API}RunState').text
        log(LOGINFO,"process_loadrunner_task: Found RunState = " + runstate)
    except Error as e:
        log(LOGERROR,"process_loadrunner_task: Did not find RunState in XML response content")
        return 

    add_request_log("REQUEST: " + url + "\nRESPONSE:" +str(response.content))
    

    if runstate == LOADRUNNER_FINISHED_STATUS:
        #######################################
        # Step 2 - if done, then send keptn event
        #######################################
        log(LOGINFO,"process_loadrunner_task: Task is finished. Processing Task")
        # set additional values required for keptn event
        task['result']="pass"
        task['status']="succeeded"
        send_keptn_event(task)

        #######################################
        # Step 3 - if done, then update database row status
        #######################################
        update_database_task(task["runid"],TASK_STATUS_DONE)
    else:
        log(LOGINFO,"process_loadrunner_task: Skipping Task processing")

def send_keptn_event(task):
    global LOGINFO
    global LOGDEBUG
    global LOGERROR
    global KEPTN_API_LOGNAME
    global KEPTN_BASE_URL
    global KEPTN_API_TOKEN

    url = KEPTN_BASE_URL + "/api/v1/event"
    theheaders = { 
        "accept": "application/json",
        "x-token": KEPTN_API_TOKEN,
        "Content-Type": "application/json" 
    }

    requestdata={
        "data": {
            "project":"REPLACE_PROJECT",
            "stage":"REPLACE_STAGE",
            "service": "REPLACE_SERVICE"
        },
        "source": "taskpoller",
        "specversion": "1.0",
        "type": "REPLACE_TYPE"
        }

    requestdata["data"]["project"]=task["project"]
    requestdata["data"]["service"]=task["service"]
    requestdata["data"]["stage"]=task["stage"]
    requestdata["type"]=task["type"]

    dt = datetime.now()
    keptnlogtext="----------------------------------------------------------------\n"
    keptnlogtext+="Date and Time  : " + str(dt) + "\n"
    keptnlogtext+="Event Type     : " + task["type"] + "\n\n"
    keptnlogtext+="Calling URL:\n" + url + "\n\n"
    keptnlogtext+="REQUEST BODY:\n" + json.dumps(requestdata,indent=2)

    # need to truncate the token as to not display the whole token
    thetoken=theheaders["x-token"]
    theheaders["x-token"]="Last 8 characters --> " + theheaders["x-token"][-8:]
    keptnlogtext+="\nHEADERS:\n" + json.dumps(theheaders,indent=2) + "\n\n"
    keptnlogtext+="----------------------------------------------------------------\n"
    keptnlogtext+="\n\n"
    f = open(KEPTN_API_LOGNAME, "a")
    f.write(keptnlogtext)
    f.close()

    # set back to original value and make the request
    theheaders["x-token"]=thetoken    
    response = requests.post(url, json=requestdata, headers=theheaders)

    log(LOGDEBUG,"send_keptn_event: HTTP status_code: " + str(response.status_code))
    log(LOGDEBUG,"send_keptn_event: HTTP reason: " + str(response.reason))

    keptnlogtext="RESPONSE\n"
    keptnlogtext+="status_code : " + str(response.status_code) + "\n"
    keptnlogtext+="reason      : " + str(response.reason) + "\n"
    keptnlogtext+="\n\n"
    f = open(KEPTN_API_LOGNAME, "a")
    f.write(keptnlogtext)
    f.close()

############################################################
# FLASK ROUTE FUNCTIONS
############################################################

@app.route('/',methods = ['GET'])
@app.route('/tasks',methods = ['GET'])
def tasks():
    global conn
    args = request.args

    title="Task Listing"
    sql = "SELECT project,service,stage,type,taskid,runid,status "
    sql+= "from task"
    filter = args.get('filter')
    if filter is not None:
        if filter != "all":
            sql+= " where status = '" + filter + "'"
            title+=" - " + filter + " only"

    cursor = conn.execute(sql)
    records = cursor.fetchall()
    num_records = str(len(records))

    return render_template("tasks.html",title=title, records = records)

@app.route('/resetlog', methods=['GET'])
def resetlogroute():
    message = resetlogs()
    return render_template("generic.html",title="Reset Logs", content=message)

@app.route('/requestlog', methods=['GET'])
def showrequestlog():
    global REQUEST_LOGNAME
    responsetext="========================================================================================================\n"
    responsetext+="REQUESTS\n"
    responsetext+="========================================================================================================\n\n"
    responsetext+=open(REQUEST_LOGNAME, "r").read()
    response=make_response(responsetext)
    response.mimetype = "text/plain"
    return response
    #return render_template("generic.html",title="Request Log", content=response)

@app.route('/applog', methods=['GET'])
def showapplog():
    global APP_LOGNAME
    responsetext="========================================================================================================\n"
    responsetext+="APP LOG\n"
    responsetext+="========================================================================================================\n\n"
    responsetext+=open(APP_LOGNAME, "r").read()
    response=make_response(responsetext)
    response.mimetype = "text/plain"
    return response
    #return render_template("generic.html",title="App Log", content=response)

@app.route('/keptnlog', methods=['GET'])
def showkeptnlog():
    global KEPTN_API_LOGNAME
    responsetext="========================================================================================================\n"
    responsetext+="REQUESTS\n"
    responsetext+="========================================================================================================\n\n"
    responsetext+=open(KEPTN_API_LOGNAME, "r").read()
    response=make_response(responsetext)
    response.mimetype = "text/plain"
    return response
    #return render_template("generic.html",title="Keptn Log", content=response)

@app.route('/addtask', methods=['POST'])
def register():
    global LOGINFO
    global LOGDEBUG
    global LOGERROR
    global request
    global conn

    # read out the values from the request
    requestdata = request.json
    
    project=requestdata["project"]
    service=requestdata["service"]
    stage=requestdata["stage"]
    type=requestdata["type"]
    taskid=requestdata["taskid"]
    runid=requestdata["runid"]
    status=TASK_STATUS_STARTED

    sql = "INSERT INTO task (project,service,stage,type,taskid,runid,status) "
    sql+= "VALUES ("
    sql+= "'" + project + "'"
    sql+= ",'" + service + "'"
    sql+= ",'" + stage + "'"
    sql+= ",'" + type + "'"
    sql+= ",'" + taskid + "'"
    sql+= ",'" + runid + "'"
    sql+= ",'" + status + "'"
    sql+= ")"

    log(LOGDEBUG,"Inserting task sql = " + sql)
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()

    return "Inserted runid = " + runid

@app.route('/simulate_loadrunner_runstatus', methods=['GET'])
def simulate_loadrunner_runstatus():
    # this simulates the response from this API
    # it will randomly return the finished status as to simulate a wait
    #https://admhelp.microfocus.com/lre/en/all/api_refs/Performance_Center_REST_API/Content/Get_Run_Status.htm
    rand=random.randrange(0, 4, 1)
    if rand==0:
        status=LOADRUNNER_FINISHED_STATUS
    else:
        status=LOADRUNNER_RUNNING_STATUS

    log(LOG_INFO,"simulate_loadrunner_runstatus: Setting status = " + status)

    xml = '<Run xmlns="http://www.hp.com/PC/REST/API">'
    xml+= '<PostRunAction>Collate And Analyze</PostRunAction>'
    xml+= '<TestID>5</TestID>'
    xml+= '<TestInstanceID>4</TestInstanceID>'
    xml+= '<TimeslotID>1015</TimeslotID>'
    xml+= '<VudsMode>false</VudsMode>'
    xml+= '<ID>14</ID>'
    xml+= '<RunState>'+status+'</RunState>'
    xml+= '</Run>'

    resp = app.make_response(xml)
    resp.mimetype = "text/xml"
    return resp

@app.route('/process', methods=['GET'])
def process_tasks():
    global LOGINFO
    global LOGDEBUG
    global LOGERROR

    #conn = create_connection(DATABASE_FILENAME)
    # get all tasks in started status
    sql = "SELECT project,service,stage,type,taskid,runid,status "
    sql+= "from task where status = '" + TASK_STATUS_STARTED + "'"
    log(LOGDEBUG,"process_tasks: Process tasks sql = " + sql)

    cursor = conn.execute(sql)
    records = cursor.fetchall()
    num_records = str(len(records))
    log(LOGINFO,"process_tasks: Record Count for tasks in " + TASK_STATUS_STARTED + " status = " + num_records)
    for row in records:
        task={}
        task["project"]=row[0]
        task["service"]=row[1]
        task["stage"]=row[2]
        task["type"]=row[3]
        task["taskid"]=row[4]
        task["runid"]=row[5]
        task["status"]=row[6]
        log(LOGDEBUG,"process_tasks: Processing Task: " + str(task))

        process_loadrunner_task(task)

    dt = datetime.now()
    return "Processed " + num_records + " tasks @ " + str(dt)

#Create the main driver function
if __name__ == '__main__':
    os.makedirs(LOG_DIR, exist_ok=True)
    get_secrets()
    conn = create_connection(DATABASE_FILENAME)
    app.run(host='0.0.0.0')
