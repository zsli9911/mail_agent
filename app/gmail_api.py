#gmail_api.py
import os
import base64
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# 定义 Gmail API 使用的权限范围
SCOPES = ['https://www.googleapis.com/auth/gmail.modify',
           'https://www.googleapis.com/auth/calendar']

def get_gmail_service():
    """获取经过身份验证的 Gmail API 服务对象，并返回 credentials"""
    creds = None
    # 检查是否已存在 token.json，用于存储用户的访问和刷新令牌
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # 如果凭据不存在或无效，则重新进行身份验证
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"刷新令牌时出错: {e}")
                return None, None
        else:
            try:
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            except FileNotFoundError:
                print("未找到 credentials.json 文件。请确保该文件存在于项目目录中。")
                return None, None
            except Exception as e:
                print(f"身份验证时出错: {e}")
                return None, None
        # 将新的令牌保存到 token.json
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    try:
        # 返回 Gmail API 服务对象和 credentials
        service = build('gmail', 'v1', credentials=creds)
        return service, creds
    except HttpError as e:
        print(f"创建 Gmail 服务对象时出错: {e}")
        return None, None

def get_calendar_service(creds):
    """获取 Google Calendar API 服务对象"""
    try:
        return build('calendar', 'v3', credentials=creds)
    except HttpError as e:
        print(f"创建 Calendar 服务对象时出错: {e}")
        return None

def get_gmail_messages(service, label_ids=None, max_results=10):
    """
    获取 Gmail 邮件列表
    :param service: Gmail API 服务对象
    :param label_ids: Gmail 标签 ID 列表（如 ['INBOX', 'TRASH']）
    :param max_results: 返回的最大邮件数量
    """
    try:
        query = {'userId': 'me', 'maxResults': max_results}
        if label_ids:
            query['labelIds'] = label_ids

        results = service.users().messages().list(**query).execute()
        messages = results.get('messages', [])
        if not messages:
            print("未找到邮件。")
            return []
        
        email_list = []
        for idx, message in enumerate(messages, start=1):
            msg = service.users().messages().get(userId='me', id=message['id'], format='full').execute()
            email_data = {
                "id": idx,
                "message_id": message['id'],
                "from": "",
                "date": "",
                "subject": "",
                "body": ""
            }
            headers = msg['payload']['headers']
            for header in headers:
                if header['name'] == 'From':
                    email_data['from'] = header['value']
                if header['name'] == 'Date':
                    email_data['date'] = header['value']
                if header['name'] == 'Subject':
                    email_data['subject'] = header['value']
            email_data['body'] = extract_body(msg['payload'])
            email_list.append(email_data)
        
        return email_list
    except Exception as e:
        print(f"获取邮件列表时出错: {e}")
        return []


def extract_body(payload):
    """提取邮件正文内容"""
    try:
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    body_data = part['body'].get('data')
                    if body_data:
                        return base64.urlsafe_b64decode(body_data).decode('utf-8')
                elif part['mimeType'] == 'multipart/alternative':
                    return extract_body(part)
        else:
            body_data = payload['body'].get('data')
            if body_data:
                return base64.urlsafe_b64decode(body_data).decode('utf-8')
    except (TypeError, ValueError, base64.binascii.Error) as e:
        print(f"提取邮件正文时出错: {e}")
    return ""

def mark_email_as_spam(service, message_id):
    """将指定邮件标记为垃圾邮件"""
    try:
        service.users().messages().modify(
            userId='me',
            id=message_id,
            body={'addLabelIds': ['SPAM']}
        ).execute()
        print(f"邮件 {message_id} 已标记为垃圾邮件。")
    except HttpError as e:
        print(f"标记邮件为垃圾邮件时出错: {e}")
    except Exception as e:
        print(f"标记垃圾邮件时出错: {e}")

def move_email_to_trash(service, message_id):
    """将指定邮件移动到垃圾箱"""
    try:
        service.users().messages().modify(
            userId='me',
            id=message_id,
            body={'addLabelIds': ['TRASH']}
        ).execute()
        print(f"The message {message_id} has been moved to the trash.")
    except HttpError as e:
        print(f"Error moving mail to trash: {e}")
    except Exception as e:
        print(f"Error moving to trash: {e}")

def add_event_to_calendar(service, summary, location, start_time, end_time):
    """将事件添加到 Google Calendar"""
    event = {
        'summary': summary,
        'location': location,
        'start': {
            'dateTime': start_time,
            'timeZone': 'Europe/Paris',  # 您可以根据需要更改时区
        },
        'end': {
            'dateTime': end_time,
            'timeZone': 'Europe/Paris',  # 您可以根据需要更改时区
        },
    }

    try:
        event_result = service.events().insert(calendarId='primary', body=event).execute()
        print(f"事件已创建: {event_result['htmlLink']}")
        return event_result['htmlLink']
    except HttpError as e:
        print(f"创建事件时出错: {e}")
        return None