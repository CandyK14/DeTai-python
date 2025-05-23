import tkinter as tk
from tkinter import ttk, messagebox, Text
import json
import os
import requests
import re
from datetime import datetime, timedelta
import uuid
import base64
import gspread
from google.oauth2.service_account import Credentials

# File để lưu trữ dữ liệu
TASKS_FILE = "tasks.json"
USERS_FILE = "users.json"
HISTORY_FILE = "task_history.json"
CONFIG_FILE = "config.json"

# Hàm mã hóa và giải mã
def encode_data(data):
    return base64.b64encode(data.encode()).decode()

def decode_data(encoded_data):
    try:
        return base64.b64decode(encoded_data.encode()).decode()
    except:
        return encoded_data

# Hàm để đọc và ghi JSON
def read_json(file_path, default_data):
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as file:
                return json.load(file)
        except:
            return default_data
    else:
        write_json(file_path, default_data)
        return default_data

def write_json(file_path, data):
    try:
        with open(file_path, 'w') as file:
            json.dump(data, file, indent=4)
    except Exception as e:
        messagebox.showerror("Lỗi", f"Không thể ghi file: {e}")

# Hàm lấy dữ liệu mẫu từ API
def fetch_sample_tasks():
    try:
        response = requests.get("https://jsonplaceholder.typicode.com/todos")
        if response.status_code == 200:
            tasks = response.json()[:5]
            formatted_tasks = [
                {
                    "id": str(uuid.uuid4()),
                    "title": task["title"],
                    "description": f"Sample task {task['id']}",
                    "assignee": "Unassigned User",
                    "status": "Todo" if not task["completed"] else "Done",
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "created_by": "System",
                    "deadline": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),
                    "notes": "",
                    "project_name": "Default Project",
                    "last_modified_by": "System",
                    "last_modified_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                } for task in tasks
            ]
            return formatted_tasks
    except:
        messagebox.showerror("Lỗi", "Không thể lấy dữ liệu từ API")
    return []

class ProjectManagementApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Quản lý Công Việc Dự Án")
        self.root.geometry("1160x700")
        self.current_user = None
        self.is_admin = False
        
        # Khởi tạo dữ liệu lịch sử
        self.history = read_json(HISTORY_FILE, [])
        
        # Đọc cấu hình Google Sheets
        self.config = read_json(CONFIG_FILE, {
            "TASK_SPREADSHEET_ID": "",
            "LOGIN_SPREADSHEET_ID": "",
            "TASK_SHEET_NAME": "Phân công",
            "LOGIN_SHEET_NAME": "Thông tin đăng nhập",
            "CREDENTIALS_FILE": "taskmanager-credentials.json"
        })
        
        # Thiết lập theme
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Tùy chỉnh style
        self.style.configure('TLabel', font=('Roboto', 12), padding=5)
        self.style.configure('TButton', font=('Roboto', 11), padding=8)
        self.style.configure('TEntry', font=('Roboto', 11), padding=5)
        self.style.configure('Treeview.Heading', font=('Roboto', 12, 'bold'), background='#4CAF50', foreground='white')
        self.style.configure('Treeview', font=('Roboto', 11), rowheight=30)
        
        # Tùy chỉnh màu button khi hover
        self.style.map('TButton',
            background=[('active', '#45a049'), ('!active', '#4CAF50')],
            foreground=[('active', 'white'), ('!active', 'white')]
        )
        
        # Khởi tạo Google Sheets
        self.SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        if not all([
            self.config["TASK_SPREADSHEET_ID"],
            self.config["LOGIN_SPREADSHEET_ID"],
            os.path.exists(self.config["CREDENTIALS_FILE"])
        ]):
            self.create_config_screen()
        else:
            self.setup_google_sheets()

    def setup_google_sheets(self):
        try:
            creds = Credentials.from_service_account_file(self.config["CREDENTIALS_FILE"], scopes=self.SCOPES)
            self.gspread_client = gspread.authorize(creds)
            self.task_spreadsheet = self.gspread_client.open_by_key(self.config["TASK_SPREADSHEET_ID"])
            try:
                self.task_sheet = self.task_spreadsheet.worksheet(self.config["TASK_SHEET_NAME"])
            except gspread.exceptions.WorksheetNotFound:
                self.task_sheet = self.task_spreadsheet.add_worksheet(title=self.config["TASK_SHEET_NAME"], rows=1000, cols=20)
            
            self.login_spreadsheet = self.gspread_client.open_by_key(self.config["LOGIN_SPREADSHEET_ID"])
            try:
                self.login_sheet = self.login_spreadsheet.worksheet(self.config["LOGIN_SHEET_NAME"])
            except gspread.exceptions.WorksheetNotFound:
                self.login_sheet = self.login_spreadsheet.add_worksheet(title=self.config["LOGIN_SHEET_NAME"], rows=1000, cols=20)
                headers = ["Username", "Password", "Full Name", "Role"]
                self.login_sheet.append_row(headers)
            
            self.sync_users_from_sheet()
            self.sync_tasks_from_sheet()
            self.create_login_screen()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể kết nối với Google Sheets: {e}")
            self.create_config_screen()

    def create_config_screen(self):
        self.clear_screen()
        
        # Frame chính với nền trắng
        main_frame = ttk.Frame(self.root, padding=20, style='Main.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True)
        self.style.configure('Main.TFrame', background='white')
        
        ttk.Label(main_frame, text="Cấu hình Google Sheets API", font=('Roboto', 16, 'bold')).grid(row=0, column=0, columnspan=2, pady=10)
        
        ttk.Label(main_frame, text="ID Google Sheet Phân công").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.task_spreadsheet_id_entry = ttk.Entry(main_frame, width=50)
        self.task_spreadsheet_id_entry.insert(0, self.config["TASK_SPREADSHEET_ID"])
        self.task_spreadsheet_id_entry.grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(main_frame, text="Tên Sheet Phân công").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        self.task_sheet_name_entry = ttk.Entry(main_frame)
        self.task_sheet_name_entry.insert(0, self.config["TASK_SHEET_NAME"])
        self.task_sheet_name_entry.grid(row=2, column=1, padx=5, pady=5)
        
        ttk.Label(main_frame, text="ID Google Sheet Đăng nhập").grid(row=3, column=0, padx=5, pady=5, sticky='e')
        self.login_spreadsheet_id_entry = ttk.Entry(main_frame, width=50)
        self.login_spreadsheet_id_entry.insert(0, self.config["LOGIN_SPREADSHEET_ID"])
        self.login_spreadsheet_id_entry.grid(row=3, column=1, padx=5, pady=5)
        
        ttk.Label(main_frame, text="Tên Sheet Đăng nhập").grid(row=4, column=0, padx=5, pady=5, sticky='e')
        self.login_sheet_name_entry = ttk.Entry(main_frame)
        self.login_sheet_name_entry.insert(0, self.config["LOGIN_SHEET_NAME"])
        self.login_sheet_name_entry.grid(row=4, column=1, padx=5, pady=5)
        
        ttk.Label(main_frame, text="Tệp Credentials (đường dẫn)").grid(row=5, column=0, padx=5, pady=5, sticky='e')
        self.credentials_file_entry = ttk.Entry(main_frame)
        self.credentials_file_entry.insert(0, self.config["CREDENTIALS_FILE"])
        self.credentials_file_entry.grid(row=5, column=1, padx=5, pady=5)
        
        ttk.Button(main_frame, text="Lưu cấu hình", command=self.save_config).grid(row=6, column=0, columnspan=2, pady=20)

    def create_login_screen(self):
        self.clear_screen()
        
        # Frame chính với nền trắng
        main_frame = ttk.Frame(self.root, padding=20, style='Main.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Logo hoặc tiêu đề
        ttk.Label(main_frame, text="Đăng nhập", font=('Roboto', 20, 'bold'), foreground='#4CAF50').pack(pady=20)
        
        # Frame cho form đăng nhập
        form_frame = ttk.Frame(main_frame)
        form_frame.pack(pady=10)
        
        ttk.Label(form_frame, text="Tên đăng nhập").grid(row=0, column=0, padx=5, pady=10, sticky='e')
        self.username_entry = ttk.Entry(form_frame, width=30)
        self.username_entry.grid(row=0, column=1, padx=5, pady=10)
        
        ttk.Label(form_frame, text="Mật khẩu").grid(row=1, column=0, padx=5, pady=10, sticky='e')
        self.password_entry = ttk.Entry(form_frame, width=30, show="*")
        self.password_entry.grid(row=1, column=1, padx=5, pady=10)
        
        # Nút đăng nhập và đăng ký
        ttk.Button(main_frame, text="Đăng nhập", command=self.login).pack(pady=10)
        ttk.Button(main_frame, text="Đăng ký", command=self.create_register_screen, style='Secondary.TButton').pack(pady=5)
        
        self.style.configure('Secondary.TButton', background='#2196F3', foreground='white')
        self.style.map('Secondary.TButton',
            background=[('active', '#1976D2'), ('!active', '#2196F3')]
        )

    def create_register_screen(self):
        self.clear_screen()
        
        main_frame = ttk.Frame(self.root, padding=20, style='Main.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_frame, text="Đăng ký", font=('Roboto', 20, 'bold'), foreground='#4CAF50').pack(pady=20)
        
        form_frame = ttk.Frame(main_frame)
        form_frame.pack(pady=10)
        
        ttk.Label(form_frame, text="Tên đăng nhập (chữ thường, không dấu)").grid(row=0, column=0, padx=5, pady=10, sticky='e')
        self.reg_username_entry = ttk.Entry(form_frame, width=30)
        self.reg_username_entry.grid(row=0, column=1, padx=5, pady=10)
        
        ttk.Label(form_frame, text="Họ tên").grid(row=1, column=0, padx=5, pady=10, sticky='e')
        self.reg_fullname_entry = ttk.Entry(form_frame, width=30)
        self.reg_fullname_entry.grid(row=1, column=1, padx=5, pady=10)
        
        ttk.Label(form_frame, text="Mật khẩu").grid(row=2, column=0, padx=5, pady=10, sticky='e')
        self.reg_password_entry = ttk.Entry(form_frame, width=30, show="*")
        self.reg_password_entry.grid(row=2, column=1, padx=5, pady=10)
        
        ttk.Button(main_frame, text="Đăng ký", command=self.register).pack(pady=10)
        ttk.Button(main_frame, text="Quay lại", command=self.create_login_screen, style='Secondary.TButton').pack(pady=5)

    def create_main_screen(self):
        self.clear_screen()
    
        # Frame chính với nền trắng
        main_frame = ttk.Frame(self.root, padding=20, style='Main.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True)
    
        # Frame cho nút đăng xuất
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(anchor="ne")
        ttk.Button(top_frame, text="Đăng xuất", command=self.create_login_screen, style='Secondary.TButton').pack(side=tk.RIGHT, padx=5)
    
        # Tiêu đề
        ttk.Label(main_frame, text="Quản lý Công Việc Dự Án", font=('Roboto', 20, 'bold'), foreground='#4CAF50').pack(pady=10)
    
        # Frame tìm kiếm
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill=tk.X, pady=5)
        ttk.Label(search_frame, text="Tìm kiếm công việc").pack(side=tk.LEFT, padx=5)
        self.search_entry = ttk.Entry(search_frame, width=30)
        self.search_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(search_frame, text="Tìm", command=self.search_tasks).pack(side=tk.LEFT, padx=5)
    
        # Frame chọn dự án
        project_frame = ttk.Frame(main_frame)
        project_frame.pack(fill=tk.X, pady=5)
        ttk.Label(project_frame, text="Dự án").pack(side=tk.LEFT, padx=5)
        self.project_var = tk.StringVar(value="Tất cả")
        projects = ["Tất cả"] + list(set(task["project_name"] for task in self.tasks))
        self.project_menu = ttk.OptionMenu(project_frame, self.project_var, "Tất cả", *projects, command=self.filter_tasks_by_project)
        self.project_menu.pack(side=tk.LEFT, padx=5)
    
        # Frame chọn chế độ xem
        view_frame = ttk.Frame(main_frame)
        view_frame.pack(fill=tk.X, pady=5)
        self.view_mode = tk.StringVar(value="mine")
        ttk.Radiobutton(view_frame, text="Công việc của tôi", variable=self.view_mode, value="mine", command=self.load_tasks).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(view_frame, text="Tất cả công việc", variable=self.view_mode, value="all", command=self.load_tasks).pack(side=tk.LEFT, padx=10)
    
        # Frame chứa Treeview
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.tree = ttk.Treeview(tree_frame, columns=("ID", "Title", "Assignee", "Status", "Deadline", "Created At"), show="headings")
        self.tree.heading("ID", text="ID")
        self.tree.heading("Title", text="Tiêu đề")
        self.tree.heading("Assignee", text="Người phụ trách")
        self.tree.heading("Status", text="Trạng thái")
        self.tree.heading("Deadline", text="Hạn chót")
        self.tree.heading("Created At", text="Ngày tạo")
        self.tree.column("ID", width=100)
        self.tree.column("Title", width=200)
        self.tree.column("Assignee", width=150)
        self.tree.column("Status", width=100)
        self.tree.column("Deadline", width=150)
        self.tree.column("Created At", width=150)
    
        # Cấu hình tag cho Treeview
        self.tree.tag_configure("overdue", background="#FFCDD2", foreground="black")
        self.tree.tag_configure("near_deadline", background="#FFF9C4", foreground="black")
        self.tree.tag_configure("normal", background="white")
        self.tree.tag_configure("even", background="#F5F5F5")
    
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True)
    
        self.tree.bind("<Double-1>", self.show_task_details)
    
        # Frame chứa các nút
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="Thêm công việc", command=self.create_task_screen).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Sửa công việc", command=self.edit_task_screen).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Xóa công việc", command=self.delete_task).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cấu hình Google Sheets", command=self.create_config_screen).pack(side=tk.LEFT, padx=5)
    
        if self.is_admin:
            ttk.Button(btn_frame, text="Xem lịch sử", command=self.show_history).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame, text="Quản lý người dùng", command=self.create_user_management_screen).pack(side=tk.LEFT, padx=5)
    
        self.load_tasks()

    def show_task_details(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
    
        task_id = self.tree.item(item, "values")[0]
        task = next((t for t in self.tasks if t["id"] == task_id), None)
        if not task:
            messagebox.showerror("Lỗi", "Không tìm thấy công việc")
            return
    
        detail_window = tk.Toplevel(self.root)
        detail_window.title(f"Chi tiết công việc: {task['title']}")
        detail_window.geometry("600x705") 
        detail_window.configure(bg='white')
    
        main_frame = ttk.Frame(detail_window, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
    
        # Frame cho nút Đóng
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(anchor="ne")
        ttk.Button(top_frame, text="Đóng", command=detail_window.destroy, style='Secondary.TButton').pack(side=tk.RIGHT, padx=5)
    
        # Tiêu đề
        ttk.Label(main_frame, text="Chi tiết Công Việc", font=('Roboto', 16, 'bold'), foreground='#4CAF50').pack(pady=10)
    
        # Frame cho form hiển thị thông tin
        form_frame = ttk.Frame(main_frame)
        form_frame.pack(pady=10, fill=tk.BOTH, expand=True)
    
        # Cột 1: Nhãn
        ttk.Label(form_frame, text="ID").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        ttk.Label(form_frame, text="Tiêu đề").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        ttk.Label(form_frame, text="Mô tả").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        ttk.Label(form_frame, text="Người phụ trách").grid(row=3, column=0, padx=5, pady=5, sticky='e')
        ttk.Label(form_frame, text="Dự án").grid(row=4, column=0, padx=5, pady=5, sticky='e')
        ttk.Label(form_frame, text="Trạng thái").grid(row=5, column=0, padx=5, pady=5, sticky='e')
        ttk.Label(form_frame, text="Hạn chót").grid(row=6, column=0, padx=5, pady=5, sticky='e')
        ttk.Label(form_frame, text="Ghi chú").grid(row=7, column=0, padx=5, pady=5, sticky='ne')
        ttk.Label(form_frame, text="Ngày tạo").grid(row=8, column=0, padx=5, pady=5, sticky='e')
        ttk.Label(form_frame, text="Người tạo").grid(row=9, column=0, padx=5, pady=5, sticky='e')
        ttk.Label(form_frame, text="Người sửa cuối").grid(row=10, column=0, padx=5, pady=5, sticky='e')
        ttk.Label(form_frame, text="Ngày sửa cuối").grid(row=11, column=0, padx=5, pady=5, sticky='e')
    
        # Cột 2: Giá trị
        ttk.Label(form_frame, text=task['id']).grid(row=0, column=1, padx=5, pady=5, sticky='w')
        ttk.Label(form_frame, text=task['title']).grid(row=1, column=1, padx=5, pady=5, sticky='w')
        ttk.Label(form_frame, text=task['description']).grid(row=2, column=1, padx=5, pady=5, sticky='w')
        ttk.Label(form_frame, text=task['assignee']).grid(row=3, column=1, padx=5, pady=5, sticky='w')
        ttk.Label(form_frame, text=task['project_name']).grid(row=4, column=1, padx=5, pady=5, sticky='w')
        ttk.Label(form_frame, text=task['status']).grid(row=5, column=1, padx=5, pady=5, sticky='w')
        ttk.Label(form_frame, text=task['deadline']).grid(row=6, column=1, padx=5, pady=5, sticky='w')
        ttk.Label(form_frame, text=task['notes'], wraplength=300).grid(row=7, column=1, padx=5, pady=5, sticky='w')
        ttk.Label(form_frame, text=task['created_at']).grid(row=8, column=1, padx=5, pady=5, sticky='w')
        ttk.Label(form_frame, text=task['created_by']).grid(row=9, column=1, padx=5, pady=5, sticky='w')
        ttk.Label(form_frame, text=task['last_modified_by']).grid(row=10, column=1, padx=5, pady=5, sticky='w')
        ttk.Label(form_frame, text=task['last_modified_at']).grid(row=11, column=1, padx=5, pady=5, sticky='w')

    def create_task_screen(self):
        self.task_window = tk.Toplevel(self.root)
        self.task_window.title("Thêm công việc")
        self.task_window.geometry("600x575") 
        self.task_window.configure(bg='white')

        main_frame = ttk.Frame(self.task_window, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Frame cho nút Lưu 
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(anchor="ne")
        ttk.Button(top_frame, text="Lưu", command=self.save_task).pack(side=tk.RIGHT, padx=5)

        # Tiêu đề
        ttk.Label(main_frame, text="Thêm Công Việc", font=('Roboto', 16, 'bold'), foreground='#4CAF50').pack(pady=10)

        # Frame cho form nhập liệu
        form_frame = ttk.Frame(main_frame)
        form_frame.pack(pady=10, fill=tk.BOTH, expand=True)

        # Cột 1: Nhãn
        ttk.Label(form_frame, text="Tiêu đề").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        ttk.Label(form_frame, text="Mô tả").grid(row=1, column=0, padx=5, pady=5, sticky='ne')  # Đổi sticky thành 'ne' để căn chỉnh giống ghi chú
        ttk.Label(form_frame, text="Người phụ trách").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        ttk.Label(form_frame, text="Dự án").grid(row=3, column=0, padx=5, pady=5, sticky='e')
        ttk.Label(form_frame, text="Trạng thái").grid(row=4, column=0, padx=5, pady=5, sticky='e')
        ttk.Label(form_frame, text="Hạn chót").grid(row=5, column=0, padx=5, pady=5, sticky='e')
        ttk.Label(form_frame, text="Ghi chú").grid(row=6, column=0, padx=5, pady=5, sticky='ne')

        # Cột 2: Trường nhập liệu
        self.title_entry = ttk.Entry(form_frame, width=30)
        self.title_entry.grid(row=0, column=1, padx=5, pady=5, sticky='w')

        self.desc_entry = Text(form_frame, height=5, width=30, font=('Roboto', 11))  # Đổi từ Entry sang Text
        self.desc_entry.grid(row=1, column=1, padx=5, pady=5, sticky='w')

        self.assignee_entry = ttk.Entry(form_frame, width=30)
        self.assignee_entry.grid(row=2, column=1, padx=5, pady=5, sticky='w')

        projects = list(set(task["project_name"] for task in self.tasks))
        if not projects:
            projects = ["Default Project"]
        self.project_entry = ttk.Entry(form_frame, width=30)
        self.project_entry.insert(0, projects[0])
        self.project_entry.grid(row=3, column=1, padx=5, pady=5, sticky='w')

        self.status_var = tk.StringVar(value="Todo")
        ttk.OptionMenu(form_frame, self.status_var, "Todo", "Todo", "In Progress", "Done").grid(row=4, column=1, padx=5, pady=5, sticky='w')

        self.deadline_entry = ttk.Entry(form_frame, width=30)
        self.deadline_entry.insert(0, (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"))
        self.deadline_entry.grid(row=5, column=1, padx=5, pady=5, sticky='w')

        self.notes_entry = Text(form_frame, height=5, width=30, font=('Roboto', 11))
        self.notes_entry.grid(row=6, column=1, padx=5, pady=5, sticky='w')

    def create_user_management_screen(self):
        if not self.is_admin:
            messagebox.showerror("Lỗi", "Chỉ quản trị viên mới có thể quản lý người dùng")
            return
        
        self.user_window = tk.Toplevel(self.root)
        self.user_window.title("Quản lý người dùng")
        self.user_window.geometry("600x500")
        self.user_window.configure(bg='white')
        
        main_frame = ttk.Frame(self.user_window, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_frame, text="Quản lý Người Dùng", font=('Roboto', 16, 'bold'), foreground='#4CAF50').pack(pady=10)
        
        self.user_tree = ttk.Treeview(main_frame, columns=("Username", "Full Name", "Role"), show="headings")
        self.user_tree.heading("Username", text="Tên đăng nhập")
        self.user_tree.heading("Full Name", text="Họ tên")
        self.user_tree.heading("Role", text="Vai trò")
        self.user_tree.column("Username", width=150)
        self.user_tree.column("Full Name", width=200)
        self.user_tree.column("Role", width=100)
        self.user_tree.pack(fill=tk.BOTH, expand=True)
        
        for username, info in self.users.items():
            self.user_tree.insert("", tk.END, values=(username, info["full_name"], info["role"]))
        
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Xóa người dùng", command=self.delete_user).pack(side=tk.LEFT, padx=5)
    #Đồng bộ người dùng từ sheet
    def sync_users_from_sheet(self):
        try:
            data = self.login_sheet.get_all_values()
            if not data or len(data) < 1:
                headers = ["Username", "Password", "Full Name", "Role"]
                self.login_sheet.append_row(headers)
                return
            
            self.users = read_json(USERS_FILE, {})
            temp_users = {}
            for username, info in list(self.users.items()):
                try:
                    decoded_username = decode_data(username)
                    temp_users[decoded_username] = {
                        "password": decode_data(info["password"]),
                        "role": info["role"],
                        "full_name": decode_data(info["full_name"])
                    }
                except:
                    temp_users[username] = info
            self.users = temp_users
            
            for row in data[1:]:
                if len(row) >= 4 and row[0].strip():
                    username, password, full_name, role = row[:4]
                    if username not in self.users:
                        self.users[username] = {
                            "password": password,
                            "role": role if role in ["user", "admin"] else "user",
                            "full_name": full_name
                        }
                    else:
                        if (self.users[username]["password"] != password or
                            self.users[username]["full_name"] != full_name or
                            self.users[username]["role"] != role):
                            self.users[username] = {
                                "password": password,
                                "role": role if role in ["user", "admin"] else "user",
                                "full_name": full_name
                            }
            
            write_json(USERS_FILE, self.encode_users_for_json(self.users))
            self.sync_users_to_login_sheet()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể đồng bộ người dùng từ Google Sheet: {e}")
    #Đồng bộ công việc từ sheet
    def sync_tasks_from_sheet(self):
        try:
            data = self.task_sheet.get_all_values()
            if not data or len(data) < 1:
                headers = [
                    "ID", "Title", "Description", "Assignee", "Project Name",
                    "Status", "Deadline", "Notes", "Created At",
                    "Created By", "Last Modified By", "Last Modified At"
                ]
                self.task_sheet.append_row(headers)
                return
            
            expected_headers = [
                "ID", "Title", "Description", "Assignee", "Project Name",
                "Status", "Deadline", "Notes", "Created At",
                "Created By", "Last Modified By", "Last Modified At"
            ]
            if data[0] != expected_headers:
                self.task_sheet.clear()
                self.task_sheet.append_row(expected_headers)
            
            self.tasks = read_json(TASKS_FILE, [])
            for row in data[1:]:
                if len(row) >= 9 and row[0].strip():
                    task_id = row[0]
                    existing_task = next((t for t in self.tasks if t["id"] == task_id), None)
                    task = {
                        "id": task_id,
                        "title": row[1] if len(row) > 1 else "",
                        "description": row[2] if len(row) > 2 else "",
                        "assignee": row[3] if len(row) > 3 else "",
                        "project_name": row[4] if len(row) > 4 else "",
                        "status": row[5] if len(row) > 5 and row[5] in ["Todo", "In Progress", "Done"] else "Todo",
                        "deadline": row[6] if len(row) > 6 else "",
                        "notes": row[7] if len(row) > 7 else "",
                        "created_at": row[8] if len(row) > 8 else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "created_by": row[9] if len(row) > 9 else "System",
                        "last_modified_by": row[10] if len(row) > 10 else "System",
                        "last_modified_at": row[11] if len(row) > 11 else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    
                    try:
                        datetime.strptime(task["deadline"], "%Y-%m-%d %H:%M:%S")
                    except:
                        task["deadline"] = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
                    
                    try:
                        datetime.strptime(task["created_at"], "%Y-%m-%d %H:%M:%S")
                    except:
                        task["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    try:
                        datetime.strptime(task["last_modified_at"], "%Y-%m-%d %H:%M:%S")
                    except:
                        task["last_modified_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    if existing_task:
                        if (existing_task["title"] != task["title"] or
                            existing_task["description"] != task["description"] or
                            existing_task["assignee"] != task["assignee"] or
                            existing_task["project_name"] != task["project_name"] or
                            existing_task["status"] != task["status"] or
                            existing_task["deadline"] != task["deadline"] or
                            existing_task["notes"] != task["notes"] or
                            existing_task["created_by"] != task["created_by"]):
                            for t in self.tasks:
                                if t["id"] == task_id:
                                    t.update(task)
                                    break
                    else:
                        self.tasks.append(task)
            
            write_json(TASKS_FILE, self.tasks)
            for task in self.tasks:
                cell = self.task_sheet.find(task["id"], in_column=1)
                if not cell:
                    self.append_task_to_sheet(task)
                else:
                    self.update_task_in_sheet(task)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể đồng bộ công việc từ Google Sheet: {e}")
    #Lưu cấu hình google sheet
    def save_config(self):
        self.config["TASK_SPREADSHEET_ID"] = self.task_spreadsheet_id_entry.get().strip()
        self.config["LOGIN_SPREADSHEET_ID"] = self.login_spreadsheet_id_entry.get().strip()
        self.config["TASK_SHEET_NAME"] = self.task_sheet_name_entry.get().strip() or "Phân công"
        self.config["LOGIN_SHEET_NAME"] = self.login_sheet_name_entry.get().strip() or "Thông tin đăng nhập"
        self.config["CREDENTIALS_FILE"] = self.credentials_file_entry.get().strip() or "taskmanager-credentials.json"
        
        if not self.config["TASK_SPREADSHEET_ID"] or not self.config["LOGIN_SPREADSHEET_ID"]:
            messagebox.showerror("Lỗi", "Vui lòng nhập ID Google Sheet cho cả Phân công và Đăng nhập")
            return
        
        if not os.path.exists(self.config["CREDENTIALS_FILE"]):
            messagebox.showerror("Lỗi", f"Không tìm thấy tệp credentials: {self.config['CREDENTIALS_FILE']}")
            return
        
        write_json(CONFIG_FILE, self.config)
        self.setup_google_sheets()
    #Mã hóa thông tin người dùng của json
    def encode_users_for_json(self, users):
        encoded_users = {}
        for username, info in users.items():
            encoded_username = encode_data(username)
            encoded_users[encoded_username] = {
                "password": encode_data(info["password"]),
                "role": info["role"],
                "full_name": encode_data(info["full_name"])
            }
        return encoded_users
    #Thêm công việc vào sheet
    def append_task_to_sheet(self, task):
        try:
            if not self.task_sheet.get_all_values():
                headers = [
                    "ID", "Title", "Description", "Assignee", "Project Name",
                    "Status", "Deadline", "Notes", "Created At",
                    "Created By", "Last Modified By", "Last Modified At"
                ]
                self.task_sheet.append_row(headers)
            
            row = [
                task['id'],
                task['title'],
                task['description'],
                task['assignee'],
                task['project_name'],
                task['status'],
                task['deadline'],
                task['notes'],
                task['created_at'],
                task['created_by'],
                task['last_modified_by'],
                task['last_modified_at']
            ]
            self.task_sheet.append_row(row)
            print(f"Đã ghi công việc '{task['title']}' lên Google Sheet (Phân công)")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể ghi lên Google Sheet (Phân công): {e}")
    #Thêm người dùng vào sheet
    def append_user_to_login_sheet(self, username, password, full_name, role):
        try:
            row = [username, password, full_name, role]
            self.login_sheet.append_row(row)
            print(f"Đã ghi thông tin đăng nhập của '{username}' lên Google Sheet (Đăng nhập)")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể ghi thông tin đăng nhập lên Google Sheet: {e}")
    #Cập nhật thông tin người dùng
    def update_user_in_login_sheet(self, username, password, full_name, role):
        try:
            cell = self.login_sheet.find(username, in_column=1)
            if cell:
                row_number = cell.row
                row = [username, password, full_name, role]
                self.login_sheet.update(f'A{row_number}:D{row_number}', [row])
                print(f"Đã cập nhật thông tin đăng nhập của '{username}' trong Google Sheet (Đăng nhập)")
            else:
                self.append_user_to_login_sheet(username, password, full_name, role)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể cập nhật thông tin đăng nhập trong Google Sheet: {e}")
    #Xóa người dùng khỏi google sheet
    def delete_user_from_login_sheet(self, username):
        try:
            cell = self.login_sheet.find(username, in_column=1)
            if cell:
                row_number = cell.row
                self.login_sheet.delete_rows(row_number)
                print(f"Đã xóa thông tin đăng nhập của '{username}' khỏi Google Sheet (Đăng nhập)")
            else:
                print(f"Không tìm thấy thông tin đăng nhập của '{username}' trong Google Sheet (Đăng nhập)")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể xóa thông tin đăng nhập khỏi Google Sheet: {e}")
    #Đồng bộ người dùng lên google sheet
    def sync_users_to_login_sheet(self):
        try:
            if not self.login_sheet.get_all_values():
                headers = ["Username", "Password", "Full Name", "Role"]
                self.login_sheet.append_row(headers)
            
            existing_users = self.login_sheet.col_values(1)[1:]
            for username, info in self.users.items():
                if username not in existing_users:
                    self.append_user_to_login_sheet(
                        username,
                        info["password"],
                        info["full_name"],
                        info["role"]
                    )
                else:
                    self.update_user_in_login_sheet(
                        username,
                        info["password"],
                        info["full_name"],
                        info["role"]
                    )
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể đồng bộ thông tin người dùng lên Google Sheet (Đăng nhập): {e}")
    #Cập nhật công việc
    def update_task_in_sheet(self, task):
        try:
            cell = self.task_sheet.find(task['id'], in_column=1)
            if cell:
                row_number = cell.row
                row = [
                    task['id'],
                    task['title'],
                    task['description'],
                    task['assignee'],
                    task['project_name'],
                    task['status'],
                    task['deadline'],
                    task['notes'],
                    task['created_at'],
                    task['created_by'],
                    task['last_modified_by'],
                    task['last_modified_at']
                ]
                self.task_sheet.update(f'A{row_number}:L{row_number}', [row])
                print(f"Đã cập nhật công việc '{task['title']}' trong Google Sheet (Phân công)")
            else:
                self.append_task_to_sheet(task)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể cập nhật Google Sheet (Phân công): {e}")
    #Xóa công việc khòi google sheet
    def delete_task_from_sheet(self, task_id):
        try:
            cell = self.task_sheet.find(task_id, in_column=1)
            if cell:
                row_number = cell.row
                self.task_sheet.delete_rows(row_number)
                print(f"Đã xóa công việc với ID '{task_id}' khỏi Google Sheet (Phân công)")
            else:
                print(f"Không tìm thấy công việc với ID '{task_id}' trong Google Sheet (Phân công)")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể xóa khỏi Google Sheet (Phân công): {e}")
    #Đăng nhập
    def login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        
        for stored_username, info in self.users.items():
            if stored_username == username and info["password"] == password:
                self.current_user = username
                self.is_admin = info["role"] == "admin"
                self.create_main_screen()
                return
        messagebox.showerror("Lỗi", "Tên đăng nhập hoặc mật khẩu không đúng")
    #Đăng ký
    def register(self):
        username = self.reg_username_entry.get()
        full_name = self.reg_fullname_entry.get()
        password = self.reg_password_entry.get()
        role = "user"

        if not username or not full_name or not password:
            messagebox.showerror("Lỗi", "Vui lòng nhập đầy đủ thông tin")
            return
    
        if not re.match(r'^[a-z0-9_-]+$', username):
            messagebox.showerror("Lỗi", "Tên đăng nhập chỉ được chứa chữ thường, số, dấu gạch dưới (_) hoặc gạch ngang (-)")
            return
    
        if username in self.users:
            messagebox.showerror("Lỗi", "Tên đăng nhập đã tồn tại")
            return
    
        self.users[username] = {
            "password": password,
            "role": role,
            "full_name": full_name
        }
        write_json(USERS_FILE, self.encode_users_for_json(self.users))
        self.append_user_to_login_sheet(username, password, full_name, role)
        messagebox.showinfo("Thành công", "Đăng ký thành công")
        self.create_login_screen()
    
    def load_tasks(self, tasks=None):
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        tasks = tasks or self.tasks
        if not self.is_admin and self.view_mode.get() == "mine":
            current_full_name = self.users[self.current_user]["full_name"]
            tasks = [task for task in tasks if task["assignee"] == current_full_name]
        
        now = datetime.now()
        for i, task in enumerate(tasks):
            deadline = datetime.strptime(task["deadline"], "%Y-%m-%d %H:%M:%S")
            time_diff = (deadline - now).total_seconds() / 3600
            
            tag = "normal"
            if time_diff <= 0 and task["status"] != "Done":
                tag = "overdue"
            elif 0 < time_diff <= 24 and task["status"] != "Done":
                tag = "near_deadline"
            
            if i % 2 == 0:
                tag = (tag, "even")
            else:
                tag = (tag,)
            
            self.tree.insert("", tk.END, values=(
                task["id"], 
                task["title"], 
                task["assignee"],
                task["status"], 
                task["deadline"], 
                task["created_at"]
            ), tags=tag)
    #Lọc công việc bằng project
    def filter_tasks_by_project(self, *args):
        project = self.project_var.get()
        if project == "Tất cả":
            filtered_tasks = self.tasks
        else:
            filtered_tasks = [task for task in self.tasks if task["project_name"] == project]
        self.load_tasks(filtered_tasks)
    #Tìm kiếm công việc
    def search_tasks(self):
        query = self.search_entry.get().lower()
        filtered_tasks = [
            task for task in self.tasks
            if query in task["title"].lower() or query in task["assignee"].lower()
        ]
        self.load_tasks(filtered_tasks)


    def save_task(self):
        title = self.title_entry.get()
        description = self.desc_entry.get("1.0", tk.END).strip()  
        assignee = self.assignee_entry.get()
        project_name = self.project_entry.get()
        status = self.status_var.get()
        deadline = self.deadline_entry.get()
        notes = self.notes_entry.get("1.0", tk.END).strip()

        if not title or not assignee or not project_name:
            messagebox.showerror("Lỗi", "Vui lòng nhập đầy đủ thông tin", parent=self.task_window)
            return

        full_names = [info["full_name"] for info in self.users.values()]
        if assignee not in full_names:
            messagebox.showerror("Lỗi", f"Người phụ trách '{assignee}' không tồn tại", parent=self.task_window)
            return

        try:
            datetime.strptime(deadline, "%Y-%m-%d %H:%M:%S")
        except:
            messagebox.showerror("Lỗi", "Hạn chót không đúng định dạng (YYYY-MM-DD HH:MM:SS)", parent=self.task_window)
            return

        task = {
            "id": str(uuid.uuid4()),
            "title": title,
            "description": description,
            "assignee": assignee,
            "project_name": project_name,
            "status": status,
            "deadline": deadline,
            "notes": notes,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "created_by": self.current_user,
            "last_modified_by": self.current_user,
            "last_modified_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        self.tasks.append(task)
        self.log_history("Created", task)
        write_json(TASKS_FILE, self.tasks)

        self.append_task_to_sheet(task)

        self.load_tasks()
        self.project_menu['menu'].delete(0, 'end')
        projects = ["Tất cả"] + list(set(task["project_name"] for task in self.tasks))
        for project in projects:
            self.project_menu['menu'].add_command(label=project, command=lambda p=project: self.project_var.set(p))

        messagebox.showinfo("Thành công", "Công việc đã được thêm", parent=self.task_window)
        self.task_window.destroy()

    #Giao diện sửa công việc
    def edit_task_screen(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showerror("Lỗi", "Vui lòng chọn một công việc")
            return

        task_id = self.tree.item(selected)["values"][0]
        task = next((t for t in self.tasks if t["id"] == task_id), None)
        if not task:
            messagebox.showerror("Lỗi", "Không tìm thấy công việc")
            return

        current_full_name = self.users[self.current_user]["full_name"]
        can_edit_full = self.is_admin or task["created_by"] == self.current_user
        can_edit_status = task["assignee"] == current_full_name

        if not (can_edit_full or can_edit_status):
            messagebox.showerror("Lỗi", "Bạn không có quyền chỉnh sửa công việc này")
            return

        self.task_window = tk.Toplevel(self.root)
        self.task_window.title("Sửa công việc")
        self.task_window.configure(bg='white')

        main_frame = ttk.Frame(self.task_window, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Frame cho nút Lưu
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(anchor="ne")
        ttk.Button(top_frame, text="Lưu", command=lambda: self.update_task(task_id)).pack(side=tk.RIGHT, padx=5)

        # Tiêu đề
        ttk.Label(main_frame, text="Sửa Công Việc", font=('Roboto', 16, 'bold'), foreground='#4CAF50').pack(pady=10)

        # Frame cho form nhập liệu
        form_frame = ttk.Frame(main_frame)
        form_frame.pack(pady=10, fill=tk.BOTH, expand=True)

        if can_edit_full:
            self.task_window.geometry("600x575")

            # Cột 1: Nhãn
            ttk.Label(form_frame, text="Tiêu đề").grid(row=0, column=0, padx=5, pady=5, sticky='e')
            ttk.Label(form_frame, text="Mô tả").grid(row=1, column=0, padx=5, pady=5, sticky='ne')  # Đổi sticky thành 'ne'
            ttk.Label(form_frame, text="Người phụ trách").grid(row=2, column=0, padx=5, pady=5, sticky='e')
            ttk.Label(form_frame, text="Dự án").grid(row=3, column=0, padx=5, pady=5, sticky='e')
            ttk.Label(form_frame, text="Trạng thái").grid(row=4, column=0, padx=5, pady=5, sticky='e')
            ttk.Label(form_frame, text="Hạn chót").grid(row=5, column=0, padx=5, pady=5, sticky='e')
            ttk.Label(form_frame, text="Ghi chú").grid(row=6, column=0, padx=5, pady=5, sticky='ne')

            # Cột 2: Trường nhập liệu
            self.title_entry = ttk.Entry(form_frame, width=30)
            self.title_entry.insert(0, task["title"])
            self.title_entry.grid(row=0, column=1, padx=5, pady=5, sticky='w')

            self.desc_entry = Text(form_frame, height=5, width=30, font=('Roboto', 11))  # Đổi từ Entry sang Text
            self.desc_entry.insert(tk.END, task["description"])
            self.desc_entry.grid(row=1, column=1, padx=5, pady=5, sticky='w')

            self.assignee_entry = ttk.Entry(form_frame, width=30)
            self.assignee_entry.insert(0, task["assignee"])
            self.assignee_entry.grid(row=2, column=1, padx=5, pady=5, sticky='w')

            self.project_entry = ttk.Entry(form_frame, width=30)
            self.project_entry.insert(0, task["project_name"])
            self.project_entry.grid(row=3, column=1, padx=5, pady=5, sticky='w')

            self.status_var = tk.StringVar(value=task["status"])
            ttk.OptionMenu(form_frame, self.status_var, task["status"], "Todo", "In Progress", "Done").grid(row=4, column=1, padx=5, pady=5, sticky='w')

            self.deadline_entry = ttk.Entry(form_frame, width=30)
            self.deadline_entry.insert(0, task["deadline"])
            self.deadline_entry.grid(row=5, column=1, padx=5, pady=5, sticky='w')

            self.notes_entry = Text(form_frame, height=5, width=30, font=('Roboto', 11))
            self.notes_entry.insert(tk.END, task["notes"])
            self.notes_entry.grid(row=6, column=1, padx=5, pady=5, sticky='w')
        else:
            self.task_window.geometry("600x300")

            # Cột 1: Nhãn
            ttk.Label(form_frame, text="Tiêu đề").grid(row=0, column=0, padx=5, pady=5, sticky='e')
            ttk.Label(form_frame, text="Người phụ trách").grid(row=1, column=0, padx=5, pady=5, sticky='e')
            ttk.Label(form_frame, text="Trạng thái").grid(row=2, column=0, padx=5, pady=5, sticky='e')

            # Cột 2: Trường nhập liệu
            ttk.Label(form_frame, text=f"{task['title']} (Không thể chỉnh sửa)", state="disabled").grid(row=0, column=1, padx=5, pady=5, sticky='w')
            ttk.Label(form_frame, text=f"{task['assignee']} (Không thể chỉnh sửa)", state="disabled").grid(row=1, column=1, padx=5, pady=5, sticky='w')
            self.status_var = tk.StringVar(value=task["status"])
            ttk.OptionMenu(form_frame, self.status_var, task["status"], "Todo", "In Progress", "Done").grid(row=2, column=1, padx=5, pady=5, sticky='w')

            # Khởi tạo các trường ẩn để tránh lỗi
            self.title_entry = ttk.Entry(form_frame, state="disabled")
            self.desc_entry = Text(form_frame, height=5, width=30, state="disabled") 
            self.assignee_entry = ttk.Entry(form_frame, state="disabled")
            self.project_entry = ttk.Entry(form_frame, state="disabled")
            self.deadline_entry = ttk.Entry(form_frame, state="disabled")
            self.notes_entry = Text(form_frame, height=5, width=30, state="disabled")
    
    def update_task(self, task_id):
        task = next((t for t in self.tasks if t["id"] == task_id), None)
        if not task:
            messagebox.showerror("Lỗi", "Không tìm thấy công việc", parent=self.task_window)
            return

        current_full_name = self.users[self.current_user]["full_name"]
        can_edit_full = self.is_admin or task["created_by"] == self.current_user
        can_edit_status = task["assignee"] == current_full_name

        if not (can_edit_full or can_edit_status):
            messagebox.showerror("Lỗi", "Bạn không có quyền chỉnh sửa công việc này", parent=self.task_window)
            return

        if can_edit_full:
            title = self.title_entry.get()
            description = self.desc_entry.get("1.0", tk.END).strip()
            assignee = self.assignee_entry.get()
            project_name = self.project_entry.get()
            status = self.status_var.get()
            deadline = self.deadline_entry.get()
            notes = self.notes_entry.get("1.0", tk.END).strip()

            if not title or not assignee or not project_name:
                messagebox.showerror("Lỗi", "Vui lòng nhập đầy đủ thông tin", parent=self.task_window)
                return

            full_names = [info["full_name"] for info in self.users.values()]
            if assignee not in full_names:
                messagebox.showerror("Lỗi", f"Người phụ trách '{assignee}' không tồn tại", parent=self.task_window)
                return

            try:
                datetime.strptime(deadline, "%Y-%m-%d %H:%M:%S")
            except:
                messagebox.showerror("Lỗi", "Hạn chót không đúng định dạng (YYYY-MM-DD HH:MM:SS)", parent=self.task_window)
                return
        else:
            status = self.status_var.get()
            title = task["title"]
            description = task["description"]
            assignee = task["assignee"]
            project_name = task["project_name"]
            deadline = task["deadline"]
            notes = task["notes"]

        for task in self.tasks:
            if task["id"] == task_id:
                task["title"] = title
                task["description"] = description
                task["assignee"] = assignee
                task["project_name"] = project_name
                task["status"] = status
                task["deadline"] = deadline
                task["notes"] = notes
                task["last_modified_by"] = self.current_user
                task["last_modified_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.log_history("Updated", task)

                self.update_task_in_sheet(task)
                break

        write_json(TASKS_FILE, self.tasks)
        self.load_tasks()
        self.project_menu['menu'].delete(0, 'end')
        projects = ["Tất cả"] + list(set(task["project_name"] for task in self.tasks))
        for project in projects:
            self.project_menu['menu'].add_command(label=project, command=lambda p=project: self.project_var.set(p))

        messagebox.showinfo("Thành công", "Công việc đã được cập nhật", parent=self.task_window)
        self.task_window.destroy()

    def delete_task(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showerror("Lỗi", "Vui lòng chọn một công việc")
            return
    
        task_id = self.tree.item(selected)["values"][0]
        task = next((t for t in self.tasks if t["id"] == task_id), None)
        if not task:
            messagebox.showerror("Lỗi", "Không tìm thấy công việc")
            return
    
        # Kiểm tra quyền xóa: chỉ admin hoặc người tạo công việc được xóa
        if not (self.is_admin or task["created_by"] == self.current_user):
            messagebox.showerror("Lỗi", "Bạn không có quyền xóa công việc này")
            return
    
        task_title = self.tree.item(selected)["values"][1]
        confirm = messagebox.askyesno("Xác nhận", f"Bạn có chắc muốn xóa công việc '{task_title}'?")
        if not confirm:
            return
    
        self.log_history("Deleted", task)
        self.tasks = [task for task in self.tasks if task["id"] != task_id]
        write_json(TASKS_FILE, self.tasks)
    
        self.delete_task_from_sheet(task_id)
    
        self.load_tasks()
        messagebox.showinfo("Thành công", "Công việc đã được xóa")
        self.project_menu['menu'].delete(0, 'end')
        projects = ["Tất cả"] + list(set(task["project_name"] for task in self.tasks))
        for project in projects:
            self.project_menu['menu'].add_command(label=project, command=lambda p=project: self.project_var.set(p))


    def log_history(self, action, task):
        history_entry = {
            "action": action,
            "task_id": task["id"],
            "title": task["title"],
            "user": self.current_user,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.history.append(history_entry)
        write_json(HISTORY_FILE, self.history)

    def show_history(self):
        if not self.is_admin:
            messagebox.showerror("Lỗi", "Chỉ quản trị viên mới có thể xem lịch sử")
            return
        
        history_window = tk.Toplevel(self.root)
        history_window.title("Lịch sử thay đổi")
        history_window.geometry("600x400")
        history_window.configure(bg='white')
        
        main_frame = ttk.Frame(history_window, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_frame, text="Lịch sử Thay đổi", font=('Roboto', 16, 'bold'), foreground='#4CAF50').pack(pady=10)
        
        tree = ttk.Treeview(main_frame, columns=("Action", "Task ID", "Title", "User", "Timestamp"), show="headings")
        tree.heading("Action", text="Hành động")
        tree.heading("Task ID", text="ID Công việc")
        tree.heading("Title", text="Tiêu đề")
        tree.heading("User", text="Người dùng")
        tree.heading("Timestamp", text="Thời gian")
        tree.pack(fill=tk.BOTH, expand=True)
        
        for entry in self.history:
            tree.insert("", tk.END, values=(
                entry["action"],
                entry["task_id"],
                entry["title"],
                entry["user"],
                entry["timestamp"]
            ))

    def delete_user(self):
        selected = self.user_tree.selection()
        if not selected:
            messagebox.showerror("Lỗi", "Vui lòng chọn một người dùng")
            return
        
        username = self.user_tree.item(selected)["values"][0]
        if username == self.current_user:
            messagebox.showerror("Lỗi", "Không thể xóa tài khoản đang đăng nhập")
            return
        
        self.delete_user_from_login_sheet(username)
        del self.users[username]
        write_json(USERS_FILE, self.encode_users_for_json(self.users))
        self.user_window.destroy()
        self.create_user_management_screen()

    def clear_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = ProjectManagementApp(root)
    root.mainloop()