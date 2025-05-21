import tkinter as tk
from tkinter import messagebox, ttk, Text
import json
import os
import requests
import re
from datetime import datetime, timedelta
import uuid
import base64
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
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

# Hàm để đọc dữ liệu từ file JSON
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

# Hàm để ghi dữ liệu vào file JSON
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

# Lớp chính của ứng dụng
class ProjectManagementApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Quản lý Công Việc Dự Án")
        self.root.geometry("1000x700")
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
        
        # Thiết lập Google Sheets API
        self.SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        
        # Kiểm tra xem cấu hình đã đầy đủ chưa
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
            
            # Kết nối với Google Sheet cho phân công
            self.task_spreadsheet = self.gspread_client.open_by_key(self.config["TASK_SPREADSHEET_ID"])
            try:
                self.task_sheet = self.task_spreadsheet.worksheet(self.config["TASK_SHEET_NAME"])
            except gspread.exceptions.WorksheetNotFound:
                self.task_sheet = self.task_spreadsheet.add_worksheet(title=self.config["TASK_SHEET_NAME"], rows=1000, cols=20)
            
            # Kết nối với Google Sheet cho đăng nhập
            self.login_spreadsheet = self.gspread_client.open_by_key(self.config["LOGIN_SPREADSHEET_ID"])
            try:
                self.login_sheet = self.login_spreadsheet.worksheet(self.config["LOGIN_SHEET_NAME"])
            except gspread.exceptions.WorksheetNotFound:
                self.login_sheet = self.login_spreadsheet.add_worksheet(title=self.config["LOGIN_SHEET_NAME"], rows=1000, cols=20)
                headers = ["Username", "Password", "Full Name", "Role"]
                self.login_sheet.append_row(headers)
            
            # Đồng bộ dữ liệu khi khởi động
            self.sync_users_from_sheet()
            self.sync_tasks_from_sheet()
            
            self.create_login_screen()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể kết nối với Google Sheets: {e}")
            self.create_config_screen()

    def sync_users_from_sheet(self):
        """Đồng bộ người dùng từ Google Sheet về ứng dụng"""
        try:
            # Đọc dữ liệu từ Google Sheet
            data = self.login_sheet.get_all_values()
            if not data or len(data) < 1:
                headers = ["Username", "Password", "Full Name", "Role"]
                self.login_sheet.append_row(headers)
                return
            
            # Đọc dữ liệu từ file JSON
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
            
            # Đọc dữ liệu từ Sheet
            for row in data[1:]:  # Bỏ qua tiêu đề
                if len(row) >= 4 and row[0].strip():  # Kiểm tra dòng hợp lệ
                    username, password, full_name, role = row[:4]
                    if username not in self.users:
                        self.users[username] = {
                            "password": password,
                            "role": role if role in ["user", "admin"] else "user",
                            "full_name": full_name
                        }
                    else:
                        # Cập nhật nếu có thay đổi
                        if (self.users[username]["password"] != password or
                            self.users[username]["full_name"] != full_name or
                            self.users[username]["role"] != role):
                            self.users[username] = {
                                "password": password,
                                "role": role if role in ["user", "admin"] else "user",
                                "full_name": full_name
                            }
            
            # Ghi lại vào file JSON
            write_json(USERS_FILE, self.encode_users_for_json(self.users))
            
            # Đồng bộ ngược lại những người dùng trong file JSON nhưng không có trong Sheet
            self.sync_users_to_login_sheet()
            
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể đồng bộ người dùng từ Google Sheet: {e}")

    def sync_tasks_from_sheet(self):
        """Đồng bộ công việc từ Google Sheet về ứng dụng"""
        try:
            # Đọc dữ liệu từ Google Sheet
            data = self.task_sheet.get_all_values()
            if not data or len(data) < 1:
                headers = [
                    "ID", "Title", "Description", "Assignee", "Project Name",
                    "Status", "Deadline", "Notes", "Created At",
                    "Last Modified By", "Last Modified At"
                ]
                self.task_sheet.append_row(headers)
                return
            
            # Đọc dữ liệu từ file JSON
            self.tasks = read_json(TASKS_FILE, [])
            
            # Đồng bộ từ Sheet
            for row in data[1:]:  # Bỏ qua tiêu đề
                if len(row) >= 11 and row[0].strip():  # Kiểm tra dòng hợp lệ
                    task_id = row[0]
                    existing_task = next((t for t in self.tasks if t["id"] == task_id), None)
                    task = {
                        "id": task_id,
                        "title": row[1],
                        "description": row[2],
                        "assignee": row[3],
                        "project_name": row[4],
                        "status": row[5] if row[5] in ["Todo", "In Progress", "Done"] else "Todo",
                        "deadline": row[6],
                        "notes": row[7],
                        "created_at": row[8],
                        "last_modified_by": row[9],
                        "last_modified_at": row[10]
                    }
                    
                    # Kiểm tra định dạng deadline
                    try:
                        datetime.strptime(task["deadline"], "%Y-%m-%d %H:%M:%S")
                    except:
                        task["deadline"] = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Kiểm tra định dạng created_at
                    try:
                        datetime.strptime(task["created_at"], "%Y-%m-%d %H:%M:%S")
                    except:
                        task["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Kiểm tra định dạng last_modified_at
                    try:
                        datetime.strptime(task["last_modified_at"], "%Y-%m-%d %H:%M:%S")
                    except:
                        task["last_modified_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    if existing_task:
                        # Cập nhật task nếu có thay đổi
                        if (existing_task["title"] != task["title"] or
                            existing_task["description"] != task["description"] or
                            existing_task["assignee"] != task["assignee"] or
                            existing_task["project_name"] != task["project_name"] or
                            existing_task["status"] != task["status"] or
                            existing_task["deadline"] != task["deadline"] or
                            existing_task["notes"] != task["notes"]):
                            for t in self.tasks:
                                if t["id"] == task_id:
                                    t.update(task)
                                    break
                    else:
                        # Thêm task mới
                        self.tasks.append(task)
            
            # Ghi lại vào file JSON
            write_json(TASKS_FILE, self.tasks)
            
            # Đồng bộ ngược lại những task trong file JSON nhưng không có trong Sheet
            for task in self.tasks:
                cell = self.task_sheet.find(task["id"], in_column=1)
                if not cell:
                    self.append_task_to_sheet(task)
                else:
                    self.update_task_in_sheet(task)
            
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể đồng bộ công việc từ Google Sheet: {e}")

    def create_config_screen(self):
        self.clear_screen()
        
        tk.Label(self.root, text="Cấu hình Google Sheets API", font=("Arial", 16)).grid(row=0, column=0, columnspan=2, pady=10)
        
        tk.Label(self.root, text="ID Google Sheet Phân công").grid(row=1, column=0, padx=5, pady=5)
        self.task_spreadsheet_id_entry = tk.Entry(self.root, width=50)
        self.task_spreadsheet_id_entry.insert(0, self.config["TASK_SPREADSHEET_ID"])
        self.task_spreadsheet_id_entry.grid(row=1, column=1, padx=5, pady=5)
        
        tk.Label(self.root, text="Tên Sheet Phân công").grid(row=2, column=0, padx=5, pady=5)
        self.task_sheet_name_entry = tk.Entry(self.root)
        self.task_sheet_name_entry.insert(0, self.config["TASK_SHEET_NAME"])
        self.task_sheet_name_entry.grid(row=2, column=1, padx=5, pady=5)
        
        tk.Label(self.root, text="ID Google Sheet Đăng nhập").grid(row=3, column=0, padx=5, pady=5)
        self.login_spreadsheet_id_entry = tk.Entry(self.root, width=50)
        self.login_spreadsheet_id_entry.insert(0, self.config["LOGIN_SPREADSHEET_ID"])
        self.login_spreadsheet_id_entry.grid(row=3, column=1, padx=5, pady=5)
        
        tk.Label(self.root, text="Tên Sheet Đăng nhập").grid(row=4, column=0, padx=5, pady=5)
        self.login_sheet_name_entry = tk.Entry(self.root)
        self.login_sheet_name_entry.insert(0, self.config["LOGIN_SHEET_NAME"])
        self.login_sheet_name_entry.grid(row=4, column=1, padx=5, pady=5)
        
        tk.Label(self.root, text="Tệp Credentials (đường dẫn)").grid(row=5, column=0, padx=5, pady=5)
        self.credentials_file_entry = tk.Entry(self.root)
        self.credentials_file_entry.insert(0, self.config["CREDENTIALS_FILE"])
        self.credentials_file_entry.grid(row=5, column=1, padx=5, pady=5)
        
        tk.Button(self.root, text="Lưu cấu hình", command=self.save_config).grid(row=6, column=0, columnspan=2, pady=10)

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

    def encode_users_for_json(self, users):
        """Mã hóa thông tin người dùng trước khi ghi vào JSON"""
        encoded_users = {}
        for username, info in users.items():
            encoded_username = encode_data(username)
            encoded_users[encoded_username] = {
                "password": encode_data(info["password"]),
                "role": info["role"],
                "full_name": encode_data(info["full_name"])
            }
        return encoded_users

    def append_task_to_sheet(self, task):
        try:
            if not self.task_sheet.get_all_values():
                headers = [
                    "ID", "Title", "Description", "Assignee", "Project Name",
                    "Status", "Deadline", "Notes", "Created At",
                    "Last Modified By", "Last Modified At"
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
                task['last_modified_by'],
                task['last_modified_at']
            ]
            self.task_sheet.append_row(row)
            print(f"Đã ghi công việc '{task['title']}' lên Google Sheet (Phân công)")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể ghi lên Google Sheet (Phân công): {e}")

    def append_user_to_login_sheet(self, username, password, full_name, role):
        """Ghi thông tin đăng nhập không mã hóa lên Google Sheet"""
        try:
            row = [username, password, full_name, role]
            self.login_sheet.append_row(row)
            print(f"Đã ghi thông tin đăng nhập của '{username}' lên Google Sheet (Đăng nhập)")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể ghi thông tin đăng nhập lên Google Sheet: {e}")

    def update_user_in_login_sheet(self, username, password, full_name, role):
        """Cập nhật thông tin đăng nhập trong Google Sheet"""
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

    def delete_user_from_login_sheet(self, username):
        """Xóa thông tin đăng nhập khỏi Google Sheet"""
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

    def sync_users_to_login_sheet(self):
        """Đồng bộ tất cả thông tin người dùng lên Google Sheet"""
        try:
            if not self.login_sheet.get_all_values():
                headers = ["Username", "Password", "Full Name", "Role"]
                self.login_sheet.append_row(headers)
            
            # Lấy tất cả username hiện có trong sheet
            existing_users = self.login_sheet.col_values(1)[1:]  # Bỏ qua tiêu đề
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
                    task['last_modified_by'],
                    task['last_modified_at']
                ]
                self.task_sheet.update(f'A{row_number}:K{row_number}', [row])
                print(f"Đã cập nhật công việc '{task['title']}' trong Google Sheet (Phân công)")
            else:
                self.append_task_to_sheet(task)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể cập nhật Google Sheet (Phân công): {e}")

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

    def create_login_screen(self):
        self.clear_screen()
        
        tk.Label(self.root, text="Đăng nhập", font=("Arial", 16)).grid(row=0, column=0, columnspan=2, pady=10)
        
        tk.Label(self.root, text="Tên đăng nhập").grid(row=1, column=0, padx=5, pady=5)
        self.username_entry = tk.Entry(self.root)
        self.username_entry.grid(row=1, column=1, padx=5, pady=5)
        
        tk.Label(self.root, text="Mật khẩu").grid(row=2, column=0, padx=5, pady=5)
        self.password_entry = tk.Entry(self.root, show="*")
        self.password_entry.grid(row=2, column=1, padx=5, pady=5)
        
        tk.Button(self.root, text="Đăng nhập", command=self.login).grid(row=3, column=0, columnspan=2, pady=10)
        tk.Button(self.root, text="Đăng ký", command=self.create_register_screen).grid(row=4, column=0, columnspan=2)

    def create_register_screen(self):
        self.clear_screen()
        
        tk.Label(self.root, text="Đăng ký", font=("Arial", 16)).grid(row=0, column=0, columnspan=2, pady=10)
        
        tk.Label(self.root, text="Tên đăng nhập (chữ thường, không dấu)").grid(row=1, column=0, padx=5, pady=5)
        self.reg_username_entry = tk.Entry(self.root)
        self.reg_username_entry.grid(row=1, column=1, padx=5, pady=5)
        
        tk.Label(self.root, text="Họ tên").grid(row=2, column=0, padx=5, pady=5)
        self.reg_fullname_entry = tk.Entry(self.root)
        self.reg_fullname_entry.grid(row=2, column=1, padx=5, pady=5)
        
        tk.Label(self.root, text="Mật khẩu").grid(row=3, column=0, padx=5, pady=5)
        self.reg_password_entry = tk.Entry(self.root, show="*")
        self.reg_password_entry.grid(row=3, column=1, padx=5, pady=5)
        
        tk.Label(self.root, text="Vai trò").grid(row=4, column=0, padx=5, pady=5)
        self.role_var = tk.StringVar(value="user")
        tk.Radiobutton(self.root, text="Người dùng", variable=self.role_var, value="user").grid(row=4, column=1, sticky="w")
        tk.Radiobutton(self.root, text="Quản trị", variable=self.role_var, value="admin").grid(row=4, column=1, sticky="e")
        
        tk.Button(self.root, text="Đăng ký", command=self.register).grid(row=5, column=0, columnspan=2, pady=10)
        tk.Button(self.root, text="Quay lại", command=self.create_login_screen).grid(row=6, column=0, columnspan=2)

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

    def register(self):
        username = self.reg_username_entry.get()
        full_name = self.reg_fullname_entry.get()
        password = self.reg_password_entry.get()
        role = self.role_var.get()
        
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

    def create_main_screen(self):
        self.clear_screen()
        
        search_frame = tk.Frame(self.root)
        search_frame.pack(fill=tk.X, padx=5, pady=5)
        tk.Label(search_frame, text="Tìm kiếm công việc").pack(side=tk.LEFT)
        self.search_entry = tk.Entry(search_frame)
        self.search_entry.pack(side=tk.LEFT, padx=5)
        tk.Button(search_frame, text="Tìm", command=self.search_tasks).pack(side=tk.LEFT)
        
        project_frame = tk.Frame(self.root)
        project_frame.pack(fill=tk.X, padx=5, pady=5)
        tk.Label(project_frame, text="Dự án").pack(side=tk.LEFT)
        self.project_var = tk.StringVar(value="All")
        projects = ["All"] + list(set(task["project_name"] for task in self.tasks))
        self.project_menu = tk.OptionMenu(project_frame, self.project_var, *projects, command=self.filter_tasks_by_project)
        self.project_menu.pack(side=tk.LEFT, padx=5)
        
        view_frame = tk.Frame(self.root)
        view_frame.pack(fill=tk.X, padx=5, pady=5)
        self.view_mode = tk.StringVar(value="mine")
        tk.Radiobutton(view_frame, text="Công việc của tôi", variable=self.view_mode, value="mine", command=self.load_tasks).pack(side=tk.LEFT)
        tk.Radiobutton(view_frame, text="Tất cả công việc", variable=self.view_mode, value="all", command=self.load_tasks).pack(side=tk.LEFT)
        
        tree_frame = tk.Frame(self.root)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.tree = ttk.Treeview(tree_frame, columns=("ID", "Title", "Assignee", "Status", "Deadline", "Created At"), show="headings")
        self.tree.heading("ID", text="ID")
        self.tree.heading("Title", text="Tiêu đề")
        self.tree.heading("Assignee", text="Người phụ trách")
        self.tree.heading("Status", text="Trạng thái")
        self.tree.heading("Deadline", text="Hạn chót")
        self.tree.heading("Created At", text="Ngày tạo")
        self.tree.column("ID", width=100)
        self.tree.column("Title", width=200)
        self.tree.column("Assignee", width=100)
        self.tree.column("Status", width=100)
        self.tree.column("Deadline", width=150)
        self.tree.column("Created At", width=150)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        self.load_tasks()
        self.check_deadline_reminders()
        
        progress_frame = tk.Frame(self.root)
        progress_frame.pack(fill=tk.X, padx=5, pady=5)
        tk.Button(progress_frame, text="Xem tiến độ", command=self.show_progress).pack(side=tk.LEFT)
        
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        tk.Button(btn_frame, text="Thêm công việc", command=self.create_task_screen).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Sửa công việc", command=self.edit_task_screen).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Xóa công việc", command=self.delete_task).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Lấy dữ liệu mẫu", command=self.fetch_and_save_sample_tasks).pack(side=tk.LEFT, padx=5)
        
        if self.is_admin:
            tk.Button(btn_frame, text="Xem lịch sử", command=self.show_history).pack(side=tk.LEFT, padx=5)
            tk.Button(btn_frame, text="Quản lý người dùng", command=self.create_user_management_screen).pack(side=tk.LEFT, padx=5)
            tk.Button(btn_frame, text="Cấu hình Google Sheets", command=self.create_config_screen).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="Đăng xuất", command=self.create_login_screen).pack(side=tk.RIGHT, padx=5)

    def load_tasks(self, tasks=None):
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        tasks = tasks or self.tasks
        if not self.is_admin and self.view_mode.get() == "mine":
            current_full_name = self.users[self.current_user]["full_name"]
            tasks = [task for task in tasks if task["assignee"] == current_full_name]
        
        if not tasks:
            messagebox.showinfo("Thông báo", "Hiện tại không có công việc nào.")
        
        for task in tasks:
            self.tree.insert("", tk.END, values=(
                task["id"], 
                task["title"], 
                task["assignee"],
                task["status"], 
                task["deadline"], 
                task["created_at"]
            ))

    def filter_tasks_by_project(self, *args):
        project = self.project_var.get()
        if project == "All":
            filtered_tasks = self.tasks
        else:
            filtered_tasks = [task for task in self.tasks if task["project_name"] == project]
        self.load_tasks(filtered_tasks)

    def search_tasks(self):
        query = self.search_entry.get().lower()
        filtered_tasks = [
            task for task in self.tasks
            if query in task["title"].lower() or query in task["assignee"].lower()
        ]
        self.load_tasks(filtered_tasks)

    def check_deadline_reminders(self):
        now = datetime.now()
        for task in self.tasks:
            deadline = datetime.strptime(task["deadline"], "%Y-%m-%d %H:%M:%S")
            time_diff = (deadline - now).total_seconds() / 3600
            if 0 < time_diff <= 24 and task["status"] != "Done":
                messagebox.showwarning("Nhắc nhở", f"Công việc '{task['title']}' sắp đến hạn: {task['deadline']}")

    def show_progress(self):
        total_tasks = len(self.tasks)
        if total_tasks == 0:
            messagebox.showinfo("Tiến độ", "Chưa có công việc nào.")
            return
        
        done_tasks = sum(1 for task in self.tasks if task["status"] == "Done")
        progress = (done_tasks / total_tasks) * 100
        
        fig, ax = plt.subplots(figsize=(5, 3))
        ax.pie([done_tasks, total_tasks - done_tasks], labels=["Done", "Remaining"], autopct='%1.1f%%', startangle=90)
        ax.set_title("Tiến độ dự án")
        
        progress_window = tk.Toplevel(self.root)
        progress_window.title("Tiến độ dự án")
        canvas = FigureCanvasTkAgg(fig, master=progress_window)
        canvas.draw()
        canvas.get_tk_widget().pack()

    def create_task_screen(self):
        self.task_window = tk.Toplevel(self.root)
        self.task_window.title("Thêm công việc")
        self.task_window.geometry("400x550")
        
        tk.Label(self.task_window, text="Tiêu đề").pack(pady=5)
        self.title_entry = tk.Entry(self.task_window)
        self.title_entry.pack(pady=5)
        
        tk.Label(self.task_window, text="Mô tả").pack(pady=5)
        self.desc_entry = tk.Entry(self.task_window)
        self.desc_entry.pack(pady=5)
        
        tk.Label(self.task_window, text="Người phụ trách (Họ tên)").pack(pady=5)
        self.assignee_entry = tk.Entry(self.task_window)
        self.assignee_entry.pack(pady=5)
        
        tk.Label(self.task_window, text="Dự án").pack(pady=5)
        projects = list(set(task["project_name"] for task in self.tasks))
        if not projects:
            projects = ["Default Project"]
        self.project_entry = tk.Entry(self.task_window)
        self.project_entry.insert(0, projects[0])
        self.project_entry.pack(pady=5)
        
        tk.Label(self.task_window, text="Trạng thái").pack(pady=5)
        self.status_var = tk.StringVar(value="Todo")
        tk.OptionMenu(self.task_window, self.status_var, "Todo", "In Progress", "Done").pack(pady=5)
        
        tk.Label(self.task_window, text="Hạn chót (YYYY-MM-DD HH:MM:SS)").pack(pady=5)
        self.deadline_entry = tk.Entry(self.task_window)
        self.deadline_entry.insert(0, (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"))
        self.deadline_entry.pack(pady=5)
        
        tk.Label(self.task_window, text="Ghi chú").pack(pady=5)
        self.notes_entry = Text(self.task_window, height=5, width=40)
        self.notes_entry.pack(pady=5)
        
        tk.Button(self.task_window, text="Lưu", command=self.save_task).pack(pady=10)

    def save_task(self):
        title = self.title_entry.get()
        description = self.desc_entry.get()
        assignee = self.assignee_entry.get()
        project_name = self.project_entry.get()
        status = self.status_var.get()
        deadline = self.deadline_entry.get()
        notes = self.notes_entry.get("1.0", tk.END).strip()
        
        if not title or not assignee or not project_name:
            messagebox.showerror("Lỗi", "Vui lòng nhập đầy đủ thông tin")
            return
        
        full_names = [info["full_name"] for info in self.users.values()]
        if assignee not in full_names:
            messagebox.showerror("Lỗi", f"Người phụ trách '{assignee}' không tồn tại")
            return
        
        try:
            datetime.strptime(deadline, "%Y-%m-%d %H:%M:%S")
        except:
            messagebox.showerror("Lỗi", "Hạn chót không đúng định dạng (YYYY-MM-DD HH:MM:SS)")
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
            "last_modified_by": self.current_user,
            "last_modified_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        self.tasks.append(task)
        self.log_history("Created", task)
        write_json(TASKS_FILE, self.tasks)
        
        self.append_task_to_sheet(task)
        
        self.load_tasks()
        self.task_window.destroy()
        self.project_menu['menu'].delete(0, 'end')
        projects = ["All"] + list(set(task["project_name"] for task in self.tasks))
        for project in projects:
            self.project_menu['menu'].add_command(label=project, command=lambda p=project: self.project_var.set(p))

    def edit_task_screen(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showerror("Lỗi", "Vui lòng chọn một công việc")
            return
        
        task_id = self.tree.item(selected)["values"][0]
        task = next((t for t in self.tasks if t["id"] == task_id), None)
        
        self.task_window = tk.Toplevel(self.root)
        self.task_window.title("Sửa công việc")
        
        if self.is_admin:
            self.task_window.geometry("400x550")
            
            tk.Label(self.task_window, text="Tiêu đề").pack(pady=5)
            self.title_entry = tk.Entry(self.task_window)
            self.title_entry.insert(0, task["title"])
            self.title_entry.pack(pady=5)
            
            tk.Label(self.task_window, text="Mô tả").pack(pady=5)
            self.desc_entry = tk.Entry(self.task_window)
            self.desc_entry.insert(0, task["description"])
            self.desc_entry.pack(pady=5)
            
            tk.Label(self.task_window, text="Người phụ trách (Họ tên)").pack(pady=5)
            self.assignee_entry = tk.Entry(self.task_window)
            self.assignee_entry.insert(0, task["assignee"])
            self.assignee_entry.pack(pady=5)
            
            tk.Label(self.task_window, text="Dự án").pack(pady=5)
            self.project_entry = tk.Entry(self.task_window)
            self.project_entry.insert(0, task["project_name"])
            self.project_entry.pack(pady=5)
            
            tk.Label(self.task_window, text="Trạng thái").pack(pady=5)
            self.status_var = tk.StringVar(value=task["status"])
            tk.OptionMenu(self.task_window, self.status_var, "Todo", "In Progress", "Done").pack(pady=5)
            
            tk.Label(self.task_window, text="Hạn chót (YYYY-MM-DD HH:MM:SS)").pack(pady=5)
            self.deadline_entry = tk.Entry(self.task_window)
            self.deadline_entry.insert(0, task["deadline"])
            self.deadline_entry.pack(pady=5)
            
            tk.Label(self.task_window, text="Ghi chú").pack(pady=5)
            self.notes_entry = Text(self.task_window, height=5, width=40)
            self.notes_entry.insert(tk.END, task["notes"])
            self.notes_entry.pack(pady=5)
        else:
            self.task_window.geometry("400x200")
            
            tk.Label(self.task_window, text=f"Tiêu đề: {task['title']} (Không thể chỉnh sửa)", state="disabled").pack(pady=5)
            tk.Label(self.task_window, text=f"Người phụ trách: {task['assignee']} (Không thể chỉnh sửa)", state="disabled").pack(pady=5)
            tk.Label(self.task_window, text="Trạng thái").pack(pady=5)
            self.status_var = tk.StringVar(value=task["status"])
            tk.OptionMenu(self.task_window, self.status_var, "Todo", "In Progress", "Done").pack(pady=5)
            
        tk.Button(self.task_window, text="Lưu", command=lambda: self.update_task(task_id)).pack(pady=10)

    def update_task(self, task_id):
        if self.is_admin:
            title = self.title_entry.get()
            description = self.desc_entry.get()
            assignee = self.assignee_entry.get()
            project_name = self.project_entry.get()
            status = self.status_var.get()
            deadline = self.deadline_entry.get()
            notes = self.notes_entry.get("1.0", tk.END).strip()
            
            if not title or not assignee or not project_name:
                messagebox.showerror("Lỗi", "Vui lòng nhập đầy đủ thông tin")
                return
            
            full_names = [info["full_name"] for info in self.users.values()]
            if assignee not in full_names:
                messagebox.showerror("Lỗi", f"Người phụ trách '{assignee}' không tồn tại")
                return
            
            try:
                datetime.strptime(deadline, "%Y-%m-%d %H:%M:%S")
            except:
                messagebox.showerror("Lỗi", "Hạn chót không đúng định dạng (YYYY-MM-DD HH:MM:SS)")
                return
        else:
            status = self.status_var.get()
            task = next((t for t in self.tasks if t["id"] == task_id), None)
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
        self.task_window.destroy()
        self.project_menu['menu'].delete(0, 'end')
        projects = ["All"] + list(set(task["project_name"] for task in self.tasks))
        for project in projects:
            self.project_menu['menu'].add_command(label=project, command=lambda p=project: self.project_var.set(p))

    def delete_task(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showerror("Lỗi", "Vui lòng chọn một công việc")
            return
        
        if not self.is_admin:
            messagebox.showerror("Lỗi", "Chỉ quản trị viên mới có thể xóa công việc")
            return
        
        task_id = self.tree.item(selected)["values"][0]
        task_title = self.tree.item(selected)["values"][1]
        task = next((t for t in self.tasks if t["id"] == task_id), None)
        
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
        projects = ["All"] + list(set(task["project_name"] for task in self.tasks))
        for project in projects:
            self.project_menu['menu'].add_command(label=project, command=lambda p=project: self.project_var.set(p))

    def fetch_and_save_sample_tasks(self):
        if not self.is_admin:
            messagebox.showerror("Lỗi", "Chỉ quản trị viên mới có thể lấy dữ liệu mẫu")
            return
        
        sample_tasks = fetch_sample_tasks()
        if sample_tasks:
            self.tasks.extend(sample_tasks)
            for task in sample_tasks:
                self.log_history("Created (Sample)", task)
                self.append_task_to_sheet(task)
            write_json(TASKS_FILE, self.tasks)
            self.load_tasks()
            self.project_menu['menu'].delete(0, 'end')
            projects = ["All"] + list(set(task["project_name"] for task in self.tasks))
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
        
        tree = ttk.Treeview(history_window, columns=("Action", "Task ID", "Title", "User", "Timestamp"), show="headings")
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

    def create_user_management_screen(self):
        if not self.is_admin:
            messagebox.showerror("Lỗi", "Chỉ quản trị viên mới có thể quản lý người dùng")
            return
        
        self.user_window = tk.Toplevel(self.root)
        self.user_window.title("Quản lý người dùng")
        self.user_window.geometry("600x400")
        
        self.user_tree = ttk.Treeview(self.user_window, columns=("Username", "Full Name", "Role"), show="headings")
        self.user_tree.heading("Username", text="Tên đăng nhập")
        self.user_tree.heading("Full Name", text="Họ tên")
        self.user_tree.heading("Role", text="Vai trò")
        self.user_tree.pack(fill=tk.BOTH, expand=True)
        
        for username, info in self.users.items():
            self.user_tree.insert("", tk.END, values=(username, info["full_name"], info["role"]))
        
        btn_frame = tk.Frame(self.user_window)
        btn_frame.pack(pady=10)
        
        tk.Button(btn_frame, text="Xóa người dùng", command=self.delete_user).pack(side=tk.LEFT, padx=5)

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