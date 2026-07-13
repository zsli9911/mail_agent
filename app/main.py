import tkinter as tk
from email_analyzer import EmailAnalyzerApp
from gmail_api import get_gmail_service

if __name__ == '__main__':
    root = tk.Tk()
    service, creds = get_gmail_service()
    if service and creds:  # 检查是否成功获取 service 和 creds
        app = EmailAnalyzerApp(root, service, creds)  # 传递 creds
        app.load_calendar_events()  # 加载日历事件
        root.mainloop()
    else:
        print("未能成功创建 Gmail 服务或获取凭据。请检查您的设置。")
