from datetime import datetime
from getpass import getpass
from ssl import create_default_context
from smtplib import SMTP_SSL
from email.message import EmailMessage

CONFIG_FILE = '.config'
RECEIVERS = ['vladmoldovan56@gmail.com','octavbirsan@gmail.com', 'adrian_steau@yahoo.com', 'sirbu96vlad@gmail.com', 'bogdanrogojan96@gmail.com', 'barb.alin.gabriel.pp@gmail.com']
RECEIVERS_SHORTLIST = ['vladmoldovan56@gmail.com', 'adrian_steau@yahoo.com', 'sirbu96vlad@gmail.com']

def get_credentials(account='email'):
    with open(CONFIG_FILE) as f:
        lines = f.readlines()

    for idx, line in enumerate(lines):
        if line.rstrip('\n') == f'[{account}]':
            break

    user = (lines[idx+1].rstrip('\n').split('='))[1]
    pw = lines[idx+2].rstrip('\n').split('=')[1]

    return user, pw


def send_mail_alert(alert_message):
    time_now = datetime.now().isoformat(' ', 'seconds')

    sender, password = get_credentials()

    msg = EmailMessage()
    msg.set_content(alert_message)
    msg['Subject'] = f"{time_now}: Stockers signals for today."
    msg['From'] = sender
    msg['To'] = RECEIVERS_SHORTLIST

    context = create_default_context()
    with SMTP_SSL("smtp.gmail.com", port=465, context=context) as server:
        server.login(sender, password)
        server.send_message(msg)
        print("Email alert sent successfully!")