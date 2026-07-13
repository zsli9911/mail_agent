import os
import base64
import json
import tkinter as tk
from tkinter import messagebox
import requests
import google.auth
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# 仅读取邮件的授权范围
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

class EmailAnalyzerApp:
    def __init__(self, root, service):
        self.root = root
        self.service = service
        self.root.title("Gmail 邮件助手")
        self.email_list = []

        # 邮件列表框
        self.email_listbox = tk.Listbox(root, width=60, height=15)
        self.email_listbox.grid(row=0, column=0, padx=10, pady=10)

        # 按钮：加载邮件
        self.load_button = tk.Button(root, text="加载邮件", command=self.load_emails)
        self.load_button.grid(row=1, column=0, padx=10, pady=10)

        # 按钮：分析选中的邮件
        self.analyze_button = tk.Button(root, text="分析邮件", command=self.analyze_selected_email)
        self.analyze_button.grid(row=2, column=0, padx=10, pady=10)

        # 分析结果框
        self.result_text = tk.Text(root, width=60, height=15)
        self.result_text.grid(row=0, column=1, rowspan=3, padx=10, pady=10)

    def load_emails(self):
        """从 Gmail API 加载邮件并显示在列表中"""
        emails = get_gmail_messages(self.service, max_results=20)
        self.email_list = emails
        self.email_listbox.delete(0, tk.END)

        for email in emails:
            self.email_listbox.insert(tk.END, f"{email['id']}: {email['subject']}")

    def analyze_selected_email(self):
        """分析用户选择的邮件"""
        selection = self.email_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请选择一封邮件进行分析")
            return

        selected_email = self.email_list[selection[0]]
        analysis_result = send_to_llama_for_analysis(selected_email)

        if analysis_result:
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, analysis_result)
        else:
            messagebox.showerror("错误", "邮件分析失败")


# 获取 Gmail API 服务对象
def get_gmail_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    service = build('gmail', 'v1', credentials=creds)
    return service


# 获取 Gmail 邮件列表
def get_gmail_messages(service, max_results=10):
    results = service.users().messages().list(userId='me', maxResults=max_results).execute()
    messages = results.get('messages', [])
    if not messages:
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

        if 'parts' in msg['payload']:
            for part in msg['payload']['parts']:
                if part['mimeType'] == 'text/plain':
                    body_data = part['body']['data']
                    email_data['body'] = base64.urlsafe_b64decode(body_data).decode('utf-8')

        email_list.append(email_data)

    return email_list


# 分析邮件内容
def send_to_llama_for_analysis(email_data, server_url="http://localhost:11434/api/generate"):
    prompt = f"""
    You are an email assistant. Your task is to analyze the email and determine whether it is a commercial advertisement.
    For non-commercial emails, provide the sender's name, date, subject, and a summary of the content.
    For commercial emails, provide the subject and then a summary of other important details.
    
    From: {email_data['from']}
    Date: {email_data['date']}
    Subject: {email_data['subject']}
    
    Body: {email_data['body']}
    
    Please respond in JSON format.
    """

    payload = {
        "model": "llama3.1",
        "prompt": prompt,
        "format": "json",
        "max_tokens": 200,
        "temperature": 0.5,
        "stream": False
    }

    try:
        response = requests.post(server_url, json=payload)
        if response.status_code == 200:
            result = response.json()
            return result.get('response', '无生成结果')
        else:
            return f"请求失败，状态码: {response.status_code}, 错误消息: {response.text}"
    except requests.exceptions.RequestException as e:
        return f"请求过程中发生错误: {e}"


# 启动 Tkinter 图形界面
def run_gui():
    root = tk.Tk()
    service = get_gmail_service()
    app = EmailAnalyzerApp(root, service)
    root.mainloop()


# 启动命令行界面
def run_cli():
    service = get_gmail_service()
    emails = get_gmail_messages(service, max_results=10)

    if not emails:
        print("没有可用邮件。")
        return

    for email in emails:
        print(f"{email['id']}: {email['subject']}")

    selected_id = int(input("请输入要分析的邮件序号: "))
    selected_email = next((email for email in emails if email['id'] == selected_id), None)

    if not selected_email:
        print("选择的邮件无效。")
        return

    analysis_result = send_to_llama_for_analysis(selected_email)
    print("分析结果:", analysis_result)


if __name__ == '__main__':
        run_cli()

