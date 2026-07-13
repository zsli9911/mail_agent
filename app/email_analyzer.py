# email_anayr_app.py
import re
import json
import tkinter as tk
from tkinter import ttk, messagebox
import threading
from datetime import datetime, timedelta
from llama_api import send_to_llama_for_analysis, summarize_email_content
from gmail_api import get_gmail_messages, mark_email_as_spam, move_email_to_trash, add_event_to_calendar, get_calendar_service
from agent import process_email  # Agent 自动化工作流入口


class EmailAnalyzerApp:
    def __init__(self, root, service, creds):
        self.root = root
        self.service = service
        self.creds = creds
        self.root.title("Mail Mind")
        self.email_list = []
        self.current_view = "INBOX"  # 默认加载 INBOX
        self.setup_ui()
        self.load_emails()  # 启动程序时自动加载邮件

    def setup_ui(self):
        # 设置窗口初始大小
        self.root.geometry("1280x800")

        # 设置主界面的网格布局
        self.root.grid_rowconfigure(0, weight=1)  # 第一行权重（邮件列表和待办事项）
        self.root.grid_rowconfigure(1, weight=0)  # 第二行权重（下拉菜单/按钮区域）
        self.root.grid_rowconfigure(2, weight=1)  # 第三行权重（邮件内容和加载提示）
        self.root.grid_columnconfigure(0, weight=1)  # 第一列权重（邮件列表和内容）
        self.root.grid_columnconfigure(1, weight=1)  # 第二列权重（待办事项和加载提示）

        # 区块1：邮件列表
        email_columns = ("id", "subject", "date", "from", "category")
        self.email_tree = ttk.Treeview(self.root, columns=email_columns, show='headings', selectmode="extended")
        self.email_tree.heading("id", text="ID")
        self.email_tree.heading("subject", text="Subject")
        self.email_tree.heading("date", text="Date")
        self.email_tree.heading("from", text="Sender")
        self.email_tree.heading("category", text="Category")
        self.email_tree.column("id", width=25, anchor="center")
        self.email_tree.column("subject", width=120, anchor="w")
        self.email_tree.column("date", width=80, anchor="center")
        self.email_tree.column("from", width=100, anchor="w")
        self.email_tree.column("category", width=80, anchor="center")
        self.email_tree.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.email_tree.bind('<<TreeviewSelect>>', self.on_email_select)

        # 区块3：待办事项（事件表格）

        event_frame = tk.Frame(self.root)  # 使用 Frame 包含表格和说明文字
        event_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

        # 添加说明文字
        event_label = tk.Label(event_frame, text="To-do items for the next 30 days", anchor="w", font=("Arial", 12, "bold"))
        event_label.pack(side="top", fill="x", padx=5, pady=5)

        # 添加事件表格
        event_columns = ("start_time", "Subject", "location")
        self.event_tree = ttk.Treeview(event_frame, columns=event_columns, show='headings', selectmode="none")
        self.event_tree.heading("start_time", text="Start Time")
        self.event_tree.heading("Subject", text="Subject")
        self.event_tree.heading("location", text="Location")
        self.event_tree.column("start_time", width=150, anchor="center")
        self.event_tree.column("Subject", width=250, anchor="w")
        self.event_tree.column("location", width=200, anchor="w")
        self.event_tree.pack(side="top", fill="both", expand=True)



        # 区块5：下拉菜单和按钮区域
        button_frame = tk.Frame(self.root)
        button_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        
            # 添加下拉菜单
        self.folder_var = tk.StringVar(value="INBOX")
        self.folder_dropdown = ttk.Combobox(button_frame, textvariable=self.folder_var, state="readonly", width=8)
        self.folder_dropdown['values'] = ("INBOX", "TRASH")  # 可切换的选项
        self.folder_dropdown.bind("<<ComboboxSelected>>", self.on_folder_change)
        self.folder_dropdown.pack(side="left", padx=5)
        self.quick_analyze_button = tk.Button(button_frame, text="Categorize All", command=self.quick_analyze_emails)
        self.quick_analyze_button.pack(side="left", padx=3)
        self.extract_summary_button = tk.Button(button_frame, text="Summarize Selected", command=self.summarize_selected_emails)
        self.extract_summary_button.pack(side="left", padx=3)
        self.spam_button = tk.Button(button_frame, text="Delete", command=self.mark_selected_emails_as_spam)
        self.spam_button.pack(side="left", padx=3)
        self.add_to_calendar_button = tk.Button(button_frame, text="Add to Calendar", command=self.add_event_from_selected_email)
        self.add_to_calendar_button.pack(side="left", padx=3)
        # 一键运行 Agent 工作流：识别->动态调用工具->校验->保存状态
        self.agent_button = tk.Button(button_frame, text="Auto (Agent)", command=self.auto_process_selected_emails)
        self.agent_button.pack(side="left", padx=3)

        # 区块2：邮件内容/模型反馈
        self.result_text = tk.Text(self.root, wrap="word", width=80, height=20)
        self.result_text.grid(row=2, column=0, padx=10, pady=10, sticky="nsew")

        # 区块4：加载提示或空白
        self.loading_label = tk.Label(self.root, text="", fg="blue", anchor="center")
        self.loading_label.grid(row=2, column=1, padx=10, pady=10, sticky="nsew")

    def load_calendar_events(self):
        """从 Google Calendar 加载未来一个月的事件并显示在事件表格中"""
        try:
            calendar_service = get_calendar_service(self.creds)
            if not calendar_service:
                messagebox.showerror("Error", "Failed to connect to Google Calendar API")
                return
            
            now = datetime.utcnow().isoformat() + 'Z'  # 当前时间（UTC 格式）
            one_month_later = (datetime.utcnow() + timedelta(days=30)).isoformat() + 'Z'  # 一个月后时间

            events_result = calendar_service.events().list(
                calendarId='primary',
                timeMin=now,
                timeMax=one_month_later,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])

            # 清空表格中的旧数据
            for item in self.event_tree.get_children():
                self.event_tree.delete(item)

            # 如果没有事件，显示提示信息
            if not events:
                self.event_tree.insert("", "end", values=("No events", "", "", ""))
                return

            # 将事件添加到表格
            for event in events:
                start_time_raw = event['start'].get('dateTime', event['start'].get('date'))
                end_time_raw = event['end'].get('dateTime', event['end'].get('date'))
                summary = event.get('summary', 'No Title')
                location = event.get('location', 'No Location')

                # 格式化时间（从 ISO8601 转换为更友好的格式）
                start_time = self.format_event_time(start_time_raw)
                end_time = self.format_event_time(end_time_raw)

                # 插入表格
                self.event_tree.insert("", "end", values=(start_time, summary, location))

        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch calendar events: {e}")

    def format_event_time(self, time_str):
        """将 ISO8601 时间格式化为用户友好的格式"""
        try:
            dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))  # 转换为本地时间
            return dt.strftime("%Y-%m-%d %H:%M")  # 格式化为 YYYY-MM-DD HH:MM
        except ValueError:
            return time_str  # 如果格式化失败，返回原始字符串

    def add_event_from_selected_email(self):
        """将选中的邮件中的关键信息提取并添加到 Google Calendar"""
        selected_items = self.email_tree.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "Please select an email to add an event")
            return

        for item in selected_items:
            email_index = self.email_tree.index(item)
            selected_email = self.email_list[email_index]

            if 'summary' not in selected_email:
                messagebox.showinfo("Information", "Please summarize the email first to extract details")
                return

            summary = selected_email['summary']
            start_time = summary.get('StartTime')
            end_time = summary.get('EndTime')
            key_locations = summary.get('KeyLocations')

            if not start_time or not end_time:
                messagebox.showwarning("Warning", "Start or end time is missing in the selected email summary")
                return
            if not key_locations:
                messagebox.showwarning("Warning", "No location found in the selected email summary")
                return

            location = key_locations[0]

            calendar_service = get_calendar_service(self.creds)
            if calendar_service:
                event_link = add_event_to_calendar(calendar_service, summary['Subject'], location, start_time, end_time)
                if event_link:
                    messagebox.showinfo("Information", f"Event created successfully: {event_link}")
                else:
                    messagebox.showerror("Error", "Failed to create event")
            else:
                messagebox.showerror("Error", "Failed to connect to Google Calendar API")

    def auto_process_selected_emails(self):
        """对选中邮件运行 Agent 自动工作流：任务识别 -> 动态调用工具 -> 校验 -> 保存状态"""
        selected_items = self.email_tree.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "Please select one or more emails to auto-process")
            return

        # 记录 (界面行索引, 邮件对象)，供后台线程处理并回写界面
        selected = [(self.email_tree.index(item), self.email_list[self.email_tree.index(item)])
                    for item in selected_items]
        self.set_loading_state(True)
        threading.Thread(target=self._auto_process_thread, args=(selected,)).start()

    def _auto_process_thread(self, selected):
        """后台线程：逐封邮件执行 Agent 工作流并持久化结构化状态"""
        for idx, email in selected:
            try:
                # Agent 根据邮件内容动态选择执行路径并返回结构化状态
                state = process_email(email, self.service, self.creds)

                # 回写内存中的邮件对象，供界面显示与后续复用
                email['category'] = state['category']
                email['reasoning'] = state['reasoning']
                if state.get('summary'):
                    email['summary'] = state['summary']
                email['status'] = state['status']

                # 状态保存：持久化分类依据/时间/地点/事件/处理状态
                self._save_classifications_to_file({email['message_id']: state})
                self.root.after(0, self._update_email_category, idx, state['category'])
            except Exception as e:
                print(f"Agent 处理邮件出错: {e}")

        self.root.after(0, self.set_loading_state, False)
        self.root.after(0, self.load_calendar_events)  # 刷新日历/待办视图
        self.root.after(0, lambda: messagebox.showinfo("Message", "Agent auto-processing completed"))

    def set_loading_state(self, is_loading):
        """设置加载状态，禁用或启用交互控件"""
        state = tk.DISABLED if is_loading else tk.NORMAL

        if hasattr(self, 'folder_dropdown'):  # 确保 folder_dropdown 存在
            self.folder_dropdown.config(state=state)

        self.quick_analyze_button.config(state=state)
        self.extract_summary_button.config(state=state)
        self.spam_button.config(state=state)
        self.add_to_calendar_button.config(state=state)
        if hasattr(self, 'agent_button'):
            self.agent_button.config(state=state)

        if is_loading:
            self.loading_label.config(text="Loading...")
        else:
            self.loading_label.config(text="")

    def _load_classifications_from_file(self):
        """从文件加载分类数据"""
        try:
            with open("email_classifications.json", "r", encoding="utf-8") as f:
                classifications = json.load(f)
            print("成功加载分类数据。")
            return classifications
        except FileNotFoundError:
            print("分类文件不存在，将创建新的分类文件。")
            return {}
        except Exception as e:
            print(f"加载分类数据时出错: {e}")
            return {}


    def load_emails(self):
        """加载当前选中的邮箱文件夹中的邮件"""
        self.set_loading_state(True)
        threading.Thread(target=self._load_emails_thread).start()

    def _load_emails_thread(self):
        """后台线程加载邮件"""
        try:
            # 加载分类数据
            classifications = self._load_classifications_from_file()

            # 获取邮件列表
            emails = get_gmail_messages(self.service, label_ids=self.current_view, max_results=20)
            self.email_list = emails

            # 匹配分类
            for email in self.email_list:
                message_id = email['message_id']
                if message_id in classifications:
                    # 复用本地持久化的结构化状态：分类依据/时间/地点/事件/处理状态
                    record = classifications[message_id]
                    email['category'] = record.get("category", "")
                    email['reasoning'] = record.get("reasoning", "")
                    if record.get("summary"):
                        email['summary'] = record["summary"]
                    if record.get("status"):
                        email['status'] = record["status"]

            self.root.after(0, self._display_emails, emails)
        except Exception as e:
            self.root.after(0, messagebox.showerror, "Error", f"Error loading emails: {e}")
        finally:
            self.root.after(0, self.set_loading_state, False)


    def _display_emails(self, emails):
        """Display emails in the Treeview and make sure the category data is displayed correctly"""
        # Clear old data
        for item in self.email_tree.get_children():
            self.email_tree.delete(item)

        # Add new data
        for email in emails:
            # Get the category from the email, the default is an empty string
            category = email.get('category', "")
            self.email_tree.insert("", "end", values=(
            email['id'], # Email ID
            email['subject'], # Email subject
            email['date'], # Email date
            email['from'], # Email sender
            category # Email category
            ))

        # Print debug information
        print(f"[debug] The mail list has been updated, showing {len(emails)} emails.")


    def on_folder_change(self, event):
        """Switch mailbox folder (Inbox or Trash)"""
        # Fix the mapping logic to make sure it matches the correct Gmail label
        folder_map = {
            "inbox": ["INBOX"], # Gmail standard label
            "trash": ["TRASH"] # Gmail standard labels
        }
        
        # Get the currently selected folder and convert to lowercase match mapping
        selected_folder = self.folder_var.get().lower()
        self.current_view = folder_map.get(selected_folder, ["INBOX"]) # default back to INBOX
        
        # Debug the output to make sure it's selected and mapped correctly
        print(f"[debug] Currently selected folder: {selected_folder}, corresponding label: {self.current_view}")
        
        # Load the emails in the corresponding folder
        self.load_emails()


        
    def quick_analyze_emails(self):
        """对整个邮件列表进行快速分类分析"""
        if not self.email_list:
            messagebox.showwarning("Warning", "No messages loaded for analysis")
            return

        self.set_loading_state(True)
        threading.Thread(target=self._quick_analyze_emails_thread).start()


    def _quick_analyze_emails_thread(self):
        """线程函数，逐一分析整个邮件列表并快速分类"""
        classifications = {}  # 保存所有邮件分类的结果
        for idx, email in enumerate(self.email_list):
            try:
                analysis_result = send_to_llama_for_analysis(email)
                category, reasoning = self._parse_analysis_result(analysis_result)

                # 更新邮件分类和模型反馈
                self.email_list[idx]['category'] = category
                self.email_list[idx]['reasoning'] = reasoning

                # 将分类结果保存到字典
                classifications[email['message_id']] = {
                    "category": category,
                    "reasoning": reasoning,
                    "status": "classified"  # 处理状态：已完成分类
                }

                # 更新界面显示
                self.root.after(0, self._update_email_category, idx, category)
            except Exception as e:
                print(f"快速分析邮件时出错: {e}")

        # 分类完成后保存到文件
        self._save_classifications_to_file(classifications)

        self.root.after(0, self.set_loading_state, False)
        messagebox.showinfo("Message", "邮件列表快速分类分析完成")

    def _save_classifications_to_file(self, classifications):
        """将结构化状态合并保存到文件（保留已有摘要/状态，支持结果复用）"""
        try:
            # 先读取已有数据再合并，避免覆盖此前持久化的摘要或处理状态
            data = self._load_classifications_from_file()
            for message_id, record in classifications.items():
                existing = data.get(message_id, {})
                # 仅更新非 None 字段，防止用空值清掉已有的摘要
                existing.update({k: v for k, v in record.items() if v is not None})
                data[message_id] = existing
            with open("email_classifications.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            print("分类结果已保存到 email_classifications.json 文件中。")
        except Exception as e:
            print(f"保存分类结果时出错: {e}")

    def summarize_selected_emails(self):
        """对选中的邮件进行总结，或提示用户是否对所有标记为 Normal 的邮件进行分析"""
        selected_items = self.email_tree.selection()
        if not selected_items:
            # 如果没有选择邮件，检查是否有标记为 Normal 的邮件
            normal_emails = [email for email in self.email_list if email.get('category') == 'Normal']
            if not normal_emails:
                messagebox.showinfo("Message", "There are no messages marked as Normal to analyze")
                return

            # 提示用户是否分析所有标记为 Normal 的邮件
            confirm = messagebox.askyesno("Confirm", "No messages were selected. Do you want to analyze all messages marked as Normal?")
            if confirm:
                self.set_loading_state(True)
                threading.Thread(target=self._summarize_emails_thread, args=(normal_emails, None)).start()
            return

        # 如果选择了邮件，则只对选中的邮件进行分析
        selected_emails = [self.email_list[self.email_tree.index(item)] for item in selected_items]
        self.set_loading_state(True)
        threading.Thread(target=self._summarize_emails_thread, args=(selected_emails, selected_items)).start()


    def _summarize_emails_thread(self, emails, selected_items):
        """线程函数，对提供的邮件进行总结"""
        for idx, email in enumerate(emails):
            try:
                summary = summarize_email_content(email)
                email['summary'] = summary  # 更新邮件的摘要
                if selected_items:
                    item_id = selected_items[idx]
                    self.email_list[self.email_tree.index(item_id)]['summary'] = summary

                    # 在主线程中更新选中邮件的文本框
                    self.root.after(0, self._update_result_text, self._format_email_display(email))
            except Exception as e:
                print(f"Error summarizing Email ID {email['id']}: {e}")

        self.root.after(0, self.set_loading_state, False)
        messagebox.showinfo("Message", "Summary of selected emails completed")

    def mark_selected_emails_as_spam(self):
        """直接将选中的邮件标记为垃圾邮件或移动到垃圾箱"""
        selected_items = self.email_tree.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "Please select one or more messages to mark")
            return

        self.set_loading_state(True)

        try:
            for item in selected_items:
                email_index = self.email_tree.index(item)
                selected_email = self.email_list[email_index]

                # 直接移动到垃圾箱或标记为垃圾邮件
                move_email_to_trash(self.service, selected_email['message_id'])

                # 更新类别标签为 "TRASH"
                self.root.after(0, self._update_email_category, email_index, "TRASH")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to mark selected messages: {e}")
        finally:
            self.set_loading_state(False)
            messagebox.showinfo("Message", "Selected emails have been moved to TRASH.")
            self.load_emails()  # 刷新邮件列表


    def on_email_select(self, event):
        """当用户选择一封邮件时，显示邮件内容"""
        selected_items = self.email_tree.selection()
        if not selected_items:
            return

        email_index = self.email_tree.index(selected_items[0])
        selected_email = self.email_list[email_index]

        # 显示邮件内容
        email_content = (
            f"Subject: {selected_email.get('subject', 'N/A')}\n"
            f"Date: {selected_email.get('date', 'N/A')}\n"
            f"From: {selected_email.get('from', 'N/A')}\n\n"
            f"{selected_email.get('body', 'No content available')}\n"
        )

        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, email_content)


        # 检查 summary
        summary = selected_email.get('summary', {})
        if not summary or not isinstance(summary, dict):
            analysis_content = "No valid analysis available. You can analyze this email for more information."
        else:
            analysis_content = (
                f"--- Analysis Summary ---\n"
                f"Subject: {summary.get('Subject', 'N/A')}\n"
                f"Key Dates: {', '.join(summary.get('KeyDates', []))}\n"
                f"Start Time: {summary.get('StartTime', 'N/A')}\n"
                f"End Time: {summary.get('EndTime', 'N/A')}\n"
                f"Key Locations: {', '.join(summary.get('KeyLocations', []))}\n"
                f"Key Events: {', '.join(summary.get('KeyEvents', []))}\n"
                f"-------------------------\n"
            )

        display_text = email_content + analysis_content
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, display_text)


    def _parse_analysis_result(self, analysis_result):
        """解析分析结果以支持分类"""
        if not analysis_result:
            print("解析失败：结果为空。")
            return 'Unknown', 'Result is empty'

        try:
            category = analysis_result.get('Category', 'Unknown').strip()
            reasoning = analysis_result.get('Reasoning', 'No reasoning provided').strip()
            print(f"解析成功: Category={category}, Reasoning={reasoning}")
            return category, reasoning
        except Exception as e:
            print(f"解析分析结果出错: {e}")
            return 'Unknown', 'Parsing error'

    def _update_email_category(self, idx, category):
        """更新 Treeview 中的邮件类别"""
        item_id = self.email_tree.get_children()[idx]
        values = list(self.email_tree.item(item_id, 'values'))
        print(f"Update email category: Index={idx}, Category={category}")
        values[4] = category # Update category column
        self.email_tree.item(item_id, values=values)
    def _update_result_text(self, text):
        """更新结果文本框"""
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, text)

    def _format_email_display(self, email):
        """格式化显示邮件内容和分析结果"""
        # 过滤邮件内容中的空白和多余换行
        subject = email.get('subject', 'N/A').strip()
        date = email.get('date', 'N/A').strip()
        sender = email.get('from', 'N/A').strip()
        body = email.get('body', 'No content available').strip()
        body = re.sub(r'\n\s*\n+', '\n\n', body)  # 清理正文中的多余空行

        # 构建邮件内容部分
        email_content = (
            f"--- Email Content ---\n"
            f"Subject: {subject}\n"
            f"Date: {date}\n"
            f"From: {sender}\n"
            f"\n{body if body else 'No content available. This might be a spam email.'}\n"
            f"---------------------\n"
        )

        # 构建分析结果部分
        if 'summary' in email:
            summary = email['summary']
            analysis_content = (
                f"--- Analysis Summary ---\n"
                f"Subject: {summary['Subject']}\n"
                f"Key Dates: {', '.join(summary['KeyDates'])}\n"
                f"Key Locations: {', '.join(summary['KeyLocations'])}\n"
                f"Key Events: {', '.join(summary['KeyEvents'])}\n"
                f"-------------------------\n"
            )
        elif 'reasoning' in email:
            analysis_content = (
                f"--- Analysis Reasoning ---\n"
                f"{email['reasoning']}\n"
                f"---------------------------\n"
            )
        else:
            analysis_content = "No analysis available. You can analyze this email for more information."

        return email_content + analysis_content
