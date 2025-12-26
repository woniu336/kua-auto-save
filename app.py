#!/usr/bin/env python3
"""
夸克网盘任务管理Web应用
基于Flask的Web界面，提供与quark_manager.sh相同的功能
"""

import os
import json
import shutil
import asyncio
import aiohttp
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file, session
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'quark-manager-secret-key-2025'

# 配置文件路径
CONFIG_FILE = 'quark_config.json'
BACKUP_DIR = 'backups'

class QuarkManager:
    """夸克网盘任务管理器"""
    
    def __init__(self):
        self.config_file = CONFIG_FILE
        self.backup_dir = BACKUP_DIR
        self.ensure_directories()
        self.load_config()
        self.invalid_links_cache = {}  # 缓存失效链接结果
    
    def ensure_directories(self):
        """确保必要的目录存在"""
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)
    
    def load_config(self):
        """加载配置文件"""
        if not os.path.exists(self.config_file):
            # 创建默认配置文件
            default_config = {
                "cookies": []
            }
            self.save_config(default_config)
            return default_config
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"配置文件JSON格式错误: {e}")
            # 创建备份并返回空配置
            self.backup_config("corrupted")
            return {"cookies": []}
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return {"cookies": []}
    
    def save_config(self, config_data):
        """保存配置文件"""
        try:
            # 创建备份
            self.backup_config("before_save")
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            return False
    
    def backup_config(self, reason=""):
        """备份配置文件"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            reason_str = f"_{reason}" if reason else ""
            backup_file = os.path.join(self.backup_dir, f"quark_config_{timestamp}{reason_str}.json")
            shutil.copy2(self.config_file, backup_file)
            logger.info(f"配置文件已备份: {backup_file}")
            return backup_file
        except Exception as e:
            logger.error(f"备份配置文件失败: {e}")
            return None
    
    def restore_config(self, backup_file):
        """恢复配置文件"""
        try:
            if os.path.exists(backup_file):
                # 创建当前配置的备份
                self.backup_config("before_restore")
                shutil.copy2(backup_file, self.config_file)
                logger.info(f"配置文件已从 {backup_file} 恢复")
                return True
            return False
        except Exception as e:
            logger.error(f"恢复配置文件失败: {e}")
            return False
    
    def get_all_accounts(self):
        """获取所有账号"""
        config = self.load_config()
        return config.get("cookies", [])
    
    def get_account(self, account_index):
        """获取指定账号"""
        accounts = self.get_all_accounts()
        if 0 <= account_index < len(accounts):
            return accounts[account_index]
        return None
    
    def add_account(self, account_data):
        """添加新账号"""
        config = self.load_config()
        
        # 验证必要字段
        if not account_data.get("name") or not account_data.get("cookie"):
            return False, "账号名称和Cookie不能为空"
        
        # 设置默认值
        new_account = {
            "name": account_data["name"],
            "cookie": account_data["cookie"],
            "tasklist": [],
            "dd_bot_token": account_data.get("dd_bot_token", ""),
            "dd_bot_secret": account_data.get("dd_bot_secret", ""),
            "tg_bot_token": "",
            "tg_user_id": "",
            "crontab": ""
        }
        
        config["cookies"].append(new_account)
        if self.save_config(config):
            return True, "账号添加成功"
        return False, "账号添加失败"
    
    def update_account(self, account_index, account_data):
        """更新账号信息"""
        config = self.load_config()
        
        if 0 <= account_index < len(config["cookies"]):
            # 更新账号信息
            for key, value in account_data.items():
                if key in config["cookies"][account_index]:
                    config["cookies"][account_index][key] = value
            
            if self.save_config(config):
                return True, "账号更新成功"
        
        return False, "账号更新失败"
    
    def delete_account(self, account_index):
        """删除账号"""
        config = self.load_config()
        
        if 0 <= account_index < len(config["cookies"]):
            del config["cookies"][account_index]
            if self.save_config(config):
                return True, "账号删除成功"
        
        return False, "账号删除失败"
    
    def get_account_tasks(self, account_index):
        """获取账号的所有任务"""
        account = self.get_account(account_index)
        if account:
            return account.get("tasklist", [])
        return []
    
    def add_task(self, account_index, task_data):
        """添加任务到账号"""
        config = self.load_config()
        
        if 0 <= account_index < len(config["cookies"]):
            # 验证任务数据
            if not task_data.get("taskname") or not task_data.get("shareurl"):
                return False, "任务名称和分享链接不能为空"
            
            new_task = {
                "emby_id": "",
                "enddate": "",
                "ignore_extension": False,
                "runweek": [1, 2, 3, 4, 5, 6, 7],
                "savepath": task_data.get("savepath", task_data["taskname"]),
                "shareurl": task_data["shareurl"],
                "taskname": task_data["taskname"],
                "link_status": {
                    "last_checked": None,
                    "is_valid": None,
                    "error_message": None
                }
            }
            
            # 检测链接有效性
            link_valid, error_msg = self.check_single_link(account_index, new_task["shareurl"])
            new_task["link_status"] = {
                "last_checked": datetime.now().isoformat(),
                "is_valid": link_valid,
                "error_message": error_msg
            }
            
            config["cookies"][account_index]["tasklist"].append(new_task)
            if self.save_config(config):
                # 清除失效链接缓存
                self.clear_invalid_links_cache(account_index)
                return True, "任务添加成功"
        
        return False, "任务添加失败"
    
    def check_single_link(self, account_index, shareurl):
        """检查单个链接的有效性"""
        try:
            from quark_auto_save import Quark
            
            config = self.load_config()
            if 0 <= account_index < len(config["cookies"]):
                account = config["cookies"][account_index]
                cookie = account.get("cookie")
                
                if not cookie:
                    return False, "账号Cookie无效"
                
                # 创建Quark对象
                quark = Quark(cookie, account_index)
                
                # 检查链接
                result = quark.get_id_from_url(shareurl)
                if result is None:
                    return False, "URL格式无效"
                
                pwd_id, _ = result
                
                # 异步检查链接有效性
                async def check_link():
                    async with aiohttp.ClientSession() as session:
                        # 验证账号
                        account_info = await quark.init(session)
                        if not account_info:
                            return False, "账号验证失败"
                        
                        # 检查链接
                        is_valid, message = await quark.get_stoken(session, pwd_id)
                        return is_valid, message
                
                # 运行异步检查
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    is_valid, message = loop.run_until_complete(check_link())
                    return is_valid, message
                finally:
                    loop.close()
            
            return False, "账号不存在"
        except ImportError:
            logger.error("无法导入quark_auto_save模块")
            return False, "无法导入quark_auto_save模块"
        except Exception as e:
            logger.error(f"检查链接失败: {e}")
            return False, f"检查失败: {str(e)}"
    
    def update_task(self, account_index, task_index, task_data):
        """更新任务"""
        config = self.load_config()
        
        if (0 <= account_index < len(config["cookies"]) and 
            0 <= task_index < len(config["cookies"][account_index]["tasklist"])):
            
            task = config["cookies"][account_index]["tasklist"][task_index]
            
            # 检查分享链接是否发生变化
            old_shareurl = task.get("shareurl", "")
            new_shareurl = task_data.get("shareurl", old_shareurl)
            
            # 更新任务字段
            for key, value in task_data.items():
                if key in task:
                    task[key] = value
            
            # 如果分享链接发生变化，重新检测链接有效性
            link_changed = new_shareurl != old_shareurl
            if link_changed:
                link_valid, error_msg = self.check_single_link(account_index, new_shareurl)
                # 确保任务有link_status字段
                if "link_status" not in task:
                    task["link_status"] = {}
                task["link_status"] = {
                    "last_checked": datetime.now().isoformat(),
                    "is_valid": link_valid,
                    "error_message": error_msg
                }
            
            if self.save_config(config):
                # 智能更新失效链接缓存，而不是清除整个缓存
                self.update_invalid_links_cache(account_index, task_index, task, link_changed)
                return True, "任务更新成功"
        
        return False, "任务更新失败"
    
    def delete_task(self, account_index, task_index):
        """删除任务"""
        config = self.load_config()
        
        if (0 <= account_index < len(config["cookies"]) and 
            0 <= task_index < len(config["cookies"][account_index]["tasklist"])):
            
            del config["cookies"][account_index]["tasklist"][task_index]
            if self.save_config(config):
                return True, "任务删除成功"
        
        return False, "任务删除失败"
    
    def batch_add_tasks(self, account_index, task_file_content):
        """批量添加任务"""
        try:
            tasks_added = 0
            config = self.load_config()
            
            if 0 <= account_index < len(config["cookies"]):
                lines = task_file_content.strip().split('\n')
                
                for line in lines:
                    line = line.strip()
                    if not line or '=' not in line:
                        continue
                    
                    try:
                        # 分割任务名和URL路径
                        taskname, url_path = line.split('=', 1)
                        taskname = taskname.strip()
                        url_path = url_path.strip()
                        
                        # 构建shareurl和savepath
                        if '#/list/share=' in url_path:
                            base_url = url_path.split('#/list/share=')[0]
                            shareurl = base_url + '#/list/share'
                            savepath = url_path.split('#/list/share=')[1]
                        else:
                            shareurl = url_path
                            savepath = taskname
                        
                        # 创建新任务
                        new_task = {
                            'emby_id': '',
                            'enddate': '',
                            'ignore_extension': False,
                            'runweek': [1, 2, 3, 4, 5, 6, 7],
                            'savepath': savepath,
                            'shareurl': shareurl,
                            'taskname': taskname,
                            'link_status': {
                                'last_checked': None,
                                'is_valid': None,
                                'error_message': None
                            }
                        }
                        
                        # 检测链接有效性
                        link_valid, error_msg = self.check_single_link(account_index, new_task["shareurl"])
                        new_task["link_status"] = {
                            "last_checked": datetime.now().isoformat(),
                            "is_valid": link_valid,
                            "error_message": error_msg
                        }
                        
                        config["cookies"][account_index]["tasklist"].append(new_task)
                        tasks_added += 1
                        
                    except Exception as e:
                        logger.warning(f"解析任务行失败: {line}, 错误: {e}")
                        continue
                
                if self.save_config(config):
                    # 清除失效链接缓存
                    self.clear_invalid_links_cache(account_index)
                    return True, f"成功添加了 {tasks_added} 个任务"
            
            return False, "批量添加任务失败"
        except Exception as e:
            logger.error(f"批量添加任务异常: {e}")
            return False, f"批量添加任务异常: {str(e)}"
    
    def validate_config(self):
        """验证配置文件"""
        config = self.load_config()
        issues = []
        
        # 检查JSON格式
        try:
            json.dumps(config)  # 尝试序列化
        except Exception as e:
            issues.append(f"JSON格式错误: {e}")
        
        # 检查账号
        accounts = config.get("cookies", [])
        if not isinstance(accounts, list):
            issues.append("cookies字段必须是数组")
        
        for i, account in enumerate(accounts):
            if not isinstance(account, dict):
                issues.append(f"账号 {i+1}: 必须是对象")
                continue
            
            # 检查必需字段
            if not account.get("name"):
                issues.append(f"账号 {i+1}: 缺少名称")
            
            if not account.get("cookie"):
                issues.append(f"账号 {i+1}: 缺少Cookie")
            
            # 检查任务列表
            tasklist = account.get("tasklist", [])
            if not isinstance(tasklist, list):
                issues.append(f"账号 {i+1}: tasklist必须是数组")
        
        return issues
    
    async def check_invalid_links(self, account_index=None):
        """检查失效链接"""
        try:
            from quark_auto_save import Quark
            
            config = self.load_config()
            accounts = config.get("cookies", [])
            
            invalid_links_by_account = {}
            
            for i, account in enumerate(accounts):
                # 如果指定了account_index，只检查该账号
                if account_index is not None and i != account_index:
                    continue
                
                cookie = account.get("cookie")
                if not cookie:
                    continue
                
                # 创建Quark对象
                quark = Quark(cookie, i)
                
                # 检查任务链接
                tasklist = account.get("tasklist", [])
                invalid_links = []
                
                async with aiohttp.ClientSession() as session:
                    # 验证账号
                    account_info = await quark.init(session)
                    if not account_info:
                        logger.warning(f"账号 {account.get('name')} 验证失败，跳过链接检查")
                        continue
                    
                    # 检查每个任务的链接
                    for task_index, task in enumerate(tasklist):
                        taskname = task.get("taskname", "未知")
                        shareurl = task.get("shareurl")
                        
                        if not shareurl:
                            invalid_links.append({
                                "task_index": task_index,
                                "taskname": taskname,
                                "shareurl": "",
                                "error": "没有找到有效的分享链接"
                            })
                            continue
                        
                        try:
                            result = quark.get_id_from_url(shareurl)
                            if result is None:
                                invalid_links.append({
                                    "task_index": task_index,
                                    "taskname": taskname,
                                    "shareurl": shareurl,
                                    "error": "URL格式无效"
                                })
                                continue
                            
                            pwd_id, _ = result
                            is_valid, message = await quark.get_stoken(session, pwd_id)
                            
                            if not is_valid:
                                invalid_links.append({
                                    "task_index": task_index,
                                    "taskname": taskname,
                                    "shareurl": shareurl,
                                    "error": message
                                })
                        except Exception as e:
                            logger.error(f"检查链接失败: {taskname} - {e}")
                            invalid_links.append({
                                "task_index": task_index,
                                "taskname": taskname,
                                "shareurl": shareurl,
                                "error": f"检查失败: {str(e)}"
                            })
                
                if invalid_links:
                    invalid_links_by_account[str(i)] = {
                        "account_name": account.get("name"),
                        "account_index": i,
                        "invalid_links": invalid_links,
                        "total_tasks": len(tasklist),
                        "invalid_count": len(invalid_links)
                    }
            
            # 缓存结果
            cache_key = "all" if account_index is None else str(account_index)
            self.invalid_links_cache[cache_key] = {
                "timestamp": datetime.now().isoformat(),
                "data": invalid_links_by_account
            }
            
            return invalid_links_by_account
            
        except ImportError:
            logger.error("无法导入quark_auto_save模块")
            return {}
        except Exception as e:
            logger.error(f"检查失效链接失败: {e}")
            return {}
    
    def get_invalid_links_summary(self, account_index=None):
        """获取失效链接摘要"""
        cache_key = "all" if account_index is None else str(account_index)
        
        if cache_key in self.invalid_links_cache:
            cache_data = self.invalid_links_cache[cache_key]
            # 检查缓存是否过期（5分钟）
            cache_time = datetime.fromisoformat(cache_data["timestamp"])
            if (datetime.now() - cache_time).total_seconds() < 300:  # 5分钟
                return cache_data["data"]
        
        # 如果没有缓存或缓存过期，返回空结果
        return {}
    
    def clear_invalid_links_cache(self, account_index=None):
        """清除失效链接缓存"""
        if account_index is None:
            self.invalid_links_cache.clear()
        else:
            cache_key = str(account_index)
            if cache_key in self.invalid_links_cache:
                del self.invalid_links_cache[cache_key]
            if "all" in self.invalid_links_cache:
                del self.invalid_links_cache["all"]
    
    def update_invalid_links_cache(self, account_index, task_index, updated_task, link_changed):
        """智能更新失效链接缓存
        
        当编辑任务时，更新缓存中的该任务状态，而不是清除整个缓存
        """
        cache_key = str(account_index)
        
        # 如果缓存不存在，不需要更新
        if cache_key not in self.invalid_links_cache:
            return
        
        cache_data = self.invalid_links_cache[cache_key]
        cache_time = datetime.fromisoformat(cache_data["timestamp"])
        
        # 检查缓存是否过期（5分钟），如果过期则清除
        if (datetime.now() - cache_time).total_seconds() >= 300:
            del self.invalid_links_cache[cache_key]
            return
        
        # 获取缓存中的账号数据
        if str(account_index) not in cache_data["data"]:
            return
        
        account_cache = cache_data["data"][str(account_index)]
        invalid_links = account_cache.get("invalid_links", [])
        
        # 获取任务信息
        taskname = updated_task.get("taskname", "")
        shareurl = updated_task.get("shareurl", "")
        link_status = updated_task.get("link_status", {})
        is_valid = link_status.get("is_valid", None)
        
        # 查找缓存中是否有这个任务
        task_found = False
        for i, link in enumerate(invalid_links):
            if link.get("task_index") == task_index:
                task_found = True
                # 如果链接有效，从失效链接列表中移除
                if is_valid:
                    invalid_links.pop(i)
                else:
                    # 更新错误信息
                    link["taskname"] = taskname
                    link["shareurl"] = shareurl
                    link["error"] = link_status.get("error_message", "未知错误")
                break
        
        # 如果任务不在失效链接列表中，但链接无效，需要添加到列表中
        if not task_found and not is_valid:
            invalid_links.append({
                "task_index": task_index,
                "taskname": taskname,
                "shareurl": shareurl,
                "error": link_status.get("error_message", "未知错误")
            })
        
        # 更新缓存数据
        account_cache["invalid_links"] = invalid_links
        account_cache["invalid_count"] = len(invalid_links)
        
        # 更新缓存时间戳
        cache_data["timestamp"] = datetime.now().isoformat()
    
    def get_backup_files(self):
        """获取备份文件列表"""
        backups = []
        try:
            if os.path.exists(self.backup_dir):
                for filename in os.listdir(self.backup_dir):
                    if filename.endswith('.json') and filename.startswith('quark_config_'):
                        filepath = os.path.join(self.backup_dir, filename)
                        stat = os.stat(filepath)
                        backups.append({
                            'filename': filename,
                            'path': filepath,
                            'size': stat.st_size,
                            'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                        })
                # 按修改时间排序（最新的在前）
                backups.sort(key=lambda x: x['modified'], reverse=True)
        except Exception as e:
            logger.error(f"获取备份文件列表失败: {e}")
        
        return backups

# 创建管理器实例
manager = QuarkManager()

# ==================== 登录系统 ====================

# 简单的用户认证（硬编码用户名和密码）
# 在实际应用中，应该从数据库或配置文件中读取
VALID_USERS = {
    "admin": "admin123",
    "user": "password123"
}

def login_required(f):
    """登录验证装饰器"""
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('请先登录', 'error')
            return redirect(url_for('simple_login'))
        return f(*args, **kwargs)
    
    return decorated_function

# ==================== 路由定义 ====================

@app.route('/')
@login_required
def index():
    """首页 - 显示所有账号"""
    accounts = manager.get_all_accounts()
    return render_template('index.html', accounts=accounts)

@app.route('/account/<int:account_id>')
@login_required
def account_detail(account_id):
    """账号详情页"""
    account = manager.get_account(account_id)
    if account:
        tasks = manager.get_account_tasks(account_id)
        # 获取失效链接信息
        invalid_links_summary = manager.get_invalid_links_summary(account_id)
        invalid_links_data = invalid_links_summary.get(str(account_id)) if invalid_links_summary else None
        
        return render_template('account_detail.html', 
                             account=account, 
                             account_id=account_id, 
                             tasks=tasks,
                             invalid_links_data=invalid_links_data)
    flash('账号不存在', 'error')
    return redirect(url_for('index'))

@app.route('/add_account', methods=['GET', 'POST'])
def add_account():
    """添加新账号"""
    if request.method == 'POST':
        account_data = {
            'name': request.form.get('name'),
            'cookie': request.form.get('cookie'),
            'dd_bot_token': request.form.get('dd_bot_token', ''),
            'dd_bot_secret': request.form.get('dd_bot_secret', '')
        }
        
        success, message = manager.add_account(account_data)
        flash(message, 'success' if success else 'error')
        
        if success:
            return redirect(url_for('index'))
    
    return render_template('add_account.html')

@app.route('/account/<int:account_id>/add_task', methods=['GET', 'POST'])
def add_task(account_id):
    """添加任务到账号"""
    account = manager.get_account(account_id)
    if not account:
        flash('账号不存在', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        task_data = {
            'taskname': request.form.get('taskname'),
            'shareurl': request.form.get('shareurl'),
            'savepath': request.form.get('savepath', '')
        }
        
        success, message = manager.add_task(account_id, task_data)
        flash(message, 'success' if success else 'error')
        
        if success:
            return redirect(url_for('account_detail', account_id=account_id))
    
    return render_template('add_task.html', account=account, account_id=account_id)

@app.route('/account/<int:account_id>/edit_task/<int:task_id>', methods=['GET', 'POST'])
def edit_task(account_id, task_id):
    """编辑任务"""
    account = manager.get_account(account_id)
    if not account:
        flash('账号不存在', 'error')
        return redirect(url_for('index'))
    
    tasks = manager.get_account_tasks(account_id)
    if task_id >= len(tasks):
        flash('任务不存在', 'error')
        return redirect(url_for('account_detail', account_id=account_id))
    
    task = tasks[task_id]
    
    if request.method == 'POST':
        task_data = {
            'taskname': request.form.get('taskname'),
            'shareurl': request.form.get('shareurl'),
            'savepath': request.form.get('savepath')
        }
        
        success, message = manager.update_task(account_id, task_id, task_data)
        flash(message, 'success' if success else 'error')
        
        if success:
            return redirect(url_for('account_detail', account_id=account_id))
    
    return render_template('edit_task.html', 
                         account=account, 
                         account_id=account_id, 
                         task_id=task_id, 
                         task=task)

@app.route('/account/<int:account_id>/delete_task/<int:task_id>')
def delete_task(account_id, task_id):
    """删除任务"""
    success, message = manager.delete_task(account_id, task_id)
    flash(message, 'success' if success else 'error')
    return redirect(url_for('account_detail', account_id=account_id))

@app.route('/batch_add_tasks', methods=['GET', 'POST'])
def batch_add_tasks():
    """批量添加任务"""
    accounts = manager.get_all_accounts()
    
    if request.method == 'POST':
        account_id = int(request.form.get('account_id', -1))
        
        if account_id < 0 or account_id >= len(accounts):
            flash('请选择有效的账号', 'error')
            return render_template('batch_add_tasks.html', accounts=accounts)
        
        # 检查是文本输入还是文件上传
        task_content = request.form.get('task_content', '').strip()
        task_file = request.files.get('task_file')
        
        content_to_process = None
        source_type = None
        
        if task_content:
            # 使用文本内容
            content_to_process = task_content
            source_type = 'text'
        elif task_file and task_file.filename != '':
            # 使用文件内容
            try:
                content_to_process = task_file.read().decode('utf-8')
                source_type = 'file'
            except Exception as e:
                flash(f'读取文件失败: {str(e)}', 'error')
                return render_template('batch_add_tasks.html', accounts=accounts)
        else:
            flash('请输入任务内容或选择任务文件', 'error')
            return render_template('batch_add_tasks.html', accounts=accounts)
        
        # 处理批量添加
        if content_to_process:
            success, message = manager.batch_add_tasks(account_id, content_to_process)
            flash(message, 'success' if success else 'error')
            
            if success:
                return redirect(url_for('account_detail', account_id=account_id))
    
    return render_template('batch_add_tasks.html', accounts=accounts)

@app.route('/backup')
def backup():
    """备份管理页面"""
    manager.backup_config("manual")
    backups = manager.get_backup_files()
    return render_template('backup.html', backups=backups)

@app.route('/restore_backup/<path:backup_path>')
def restore_backup(backup_path):
    """恢复备份"""
    success = manager.restore_config(backup_path)
    if success:
        flash('配置文件恢复成功', 'success')
    else:
        flash('配置文件恢复失败', 'error')
    return redirect(url_for('backup'))

@app.route('/validate')
def validate():
    """验证配置文件"""
    config = manager.load_config()
    issues = manager.validate_config()
    
    # 构建详细的验证结果
    validation_result = {
        'is_valid': len(issues) == 0,
        'json_valid': True,
        'account_count': len(config.get('cookies', [])),
        'total_tasks': 0,
        'required_fields_valid': True,
        'backup_dir_exists': os.path.exists(manager.backup_dir),
        'accounts': [],
        'field_issues': [],
        'suggestions': []
    }
    
    # 检查JSON格式
    try:
        json.dumps(config)
    except Exception as e:
        validation_result['json_valid'] = False
        validation_result['suggestions'].append('配置文件JSON格式错误，请使用修复工具')
    
    # 统计任务和检查账号
    total_tasks = 0
    for i, account in enumerate(config.get('cookies', [])):
        task_count = len(account.get('tasklist', []))
        total_tasks += task_count
        
        account_valid = True
        if not account.get('name'):
            validation_result['required_fields_valid'] = False
            validation_result['field_issues'].append({
                'account': f"账号 {i+1}",
                'issue': '缺少名称',
                'field': 'name'
            })
            account_valid = False
            validation_result['suggestions'].append(f'账号 {i+1} 缺少名称字段')
        
        if not account.get('cookie'):
            validation_result['required_fields_valid'] = False
            validation_result['field_issues'].append({
                'account': f"账号 {i+1}",
                'issue': '缺少Cookie',
                'field': 'cookie'
            })
            account_valid = False
            validation_result['suggestions'].append(f'账号 {i+1} 缺少Cookie字段')
        
        validation_result['accounts'].append({
            'name': account.get('name', f'账号 {i+1}'),
            'task_count': task_count,
            'valid': account_valid
        })
    
    validation_result['total_tasks'] = total_tasks
    
    # 添加其他建议
    if validation_result['account_count'] == 0:
        validation_result['suggestions'].append('没有配置任何账号，请添加至少一个账号')
    
    if not validation_result['backup_dir_exists']:
        validation_result['suggestions'].append('备份目录不存在，建议创建备份目录')
    
    if total_tasks == 0:
        validation_result['suggestions'].append('没有配置任何任务，请添加任务')
    
    return render_template('validate.html', validation_result=validation_result)

@app.route('/api/accounts')
def api_accounts():
    """API: 获取所有账号"""
    accounts = manager.get_all_accounts()
    return jsonify(accounts)

@app.route('/api/account/<int:account_id>')
def api_account(account_id):
    """API: 获取指定账号"""
    account = manager.get_account(account_id)
    if account:
        return jsonify(account)
    return jsonify({'error': '账号不存在'}), 404

@app.route('/api/account/<int:account_id>/tasks')
def api_account_tasks(account_id):
    """API: 获取账号任务"""
    tasks = manager.get_account_tasks(account_id)
    return jsonify(tasks)

@app.route('/fix_json')
def fix_json():
    """修复JSON格式"""
    try:
        # 尝试读取并重新写入配置文件
        config = manager.load_config()
        success = manager.save_config(config)
        
        if success:
            flash('JSON格式修复成功', 'success')
        else:
            flash('JSON格式修复失败', 'error')
    except Exception as e:
        flash(f'修复过程中发生错误: {str(e)}', 'error')
    
    return redirect(url_for('validate'))

@app.route('/fix_account')
def fix_account():
    """修复账号字段"""
    try:
        config = manager.load_config()
        fixed_count = 0
        
        for account in config.get('cookies', []):
            # 确保必需字段存在
            if 'name' not in account or not account['name']:
                account['name'] = f'未命名账号_{fixed_count + 1}'
                fixed_count += 1
            
            if 'cookie' not in account or not account['cookie']:
                account['cookie'] = ''
                fixed_count += 1
            
            # 确保其他字段存在
            if 'tasklist' not in account:
                account['tasklist'] = []
            
            if 'dd_bot_token' not in account:
                account['dd_bot_token'] = ''
            
            if 'dd_bot_secret' not in account:
                account['dd_bot_secret'] = ''
        
        success = manager.save_config(config)
        
        if success:
            flash(f'成功修复了 {fixed_count} 个账号字段', 'success')
        else:
            flash('修复账号字段失败', 'error')
    except Exception as e:
        flash(f'修复过程中发生错误: {str(e)}', 'error')
    
    return redirect(url_for('validate'))

@app.route('/create_backup')
def create_backup():
    """创建备份目录"""
    try:
        manager.ensure_directories()
        flash('备份目录创建成功', 'success')
    except Exception as e:
        flash(f'创建备份目录失败: {str(e)}', 'error')
    
    return redirect(url_for('validate'))

@app.route('/download_backup/<filename>')
def download_backup(filename):
    """下载备份文件"""
    try:
        backup_path = os.path.join(manager.backup_dir, filename)
        if os.path.exists(backup_path):
            return send_file(backup_path, as_attachment=True)
        else:
            flash('备份文件不存在', 'error')
    except Exception as e:
        flash(f'下载备份文件失败: {str(e)}', 'error')
    
    return redirect(url_for('backup'))

@app.route('/delete_backup/<filename>')
def delete_backup(filename):
    """删除备份文件"""
    try:
        backup_path = os.path.join(manager.backup_dir, filename)
        if os.path.exists(backup_path):
            os.remove(backup_path)
            flash('备份文件删除成功', 'success')
        else:
            flash('备份文件不存在', 'error')
    except Exception as e:
        flash(f'删除备份文件失败: {str(e)}', 'error')
    
    return redirect(url_for('backup'))

@app.route('/upload_backup', methods=['POST'])
def upload_backup():
    """上传备份文件"""
    try:
        if 'backup_file' not in request.files:
            flash('没有选择文件', 'error')
            return redirect(url_for('backup'))
        
        file = request.files['backup_file']
        if file.filename is None or file.filename == '':
            flash('没有选择文件', 'error')
            return redirect(url_for('backup'))
        
        if not file.filename.lower().endswith('.json'):
            flash('只支持JSON格式的文件', 'error')
            return redirect(url_for('backup'))
        
        # 验证文件内容是否为有效的JSON
        content = file.read()
        try:
            json.loads(content.decode('utf-8'))
        except json.JSONDecodeError:
            flash('文件内容不是有效的JSON格式', 'error')
            return redirect(url_for('backup'))
        
        # 保存文件
        file.seek(0)  # 重置文件指针
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"quark_config_upload_{timestamp}.json"
        filepath = os.path.join(manager.backup_dir, filename)
        file.save(filepath)
        
        flash('备份文件上传成功', 'success')
    except Exception as e:
        flash(f'上传备份文件失败: {str(e)}', 'error')
    
    return redirect(url_for('backup'))

@app.route('/account/<int:account_id>/edit', methods=['GET', 'POST'])
def edit_account(account_id):
    """编辑账号设置"""
    account = manager.get_account(account_id)
    if not account:
        flash('账号不存在', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        account_data = {
            'name': request.form.get('name'),
            'cookie': request.form.get('cookie'),
            'dd_bot_token': request.form.get('dd_bot_token', ''),
            'dd_bot_secret': request.form.get('dd_bot_secret', ''),
            'tg_bot_token': request.form.get('tg_bot_token', ''),
            'tg_user_id': request.form.get('tg_user_id', ''),
            'crontab': request.form.get('crontab', '')
        }
        
        success, message = manager.update_account(account_id, account_data)
        flash(message, 'success' if success else 'error')
        
        if success:
            return redirect(url_for('account_detail', account_id=account_id))
    
    return render_template('edit_account.html', account=account, account_id=account_id)

@app.route('/account/<int:account_id>/execute', methods=['POST'])
def execute_account_tasks(account_id):
    """立即执行账号任务"""
    try:
        import subprocess
        import sys
        
        # 构建命令：python quark_auto_save.py quark_config.json account_id
        cmd = [sys.executable, 'quark_auto_save.py', 'quark_config.json', str(account_id)]
        
        # 在后台执行命令（非阻塞）
        if sys.platform == 'win32':
            # Windows系统
            subprocess.Popen(cmd, shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            # Linux/Mac系统
            subprocess.Popen(cmd, start_new_session=True)
        
        flash(f'已启动任务执行，请查看日志文件 quark_save.log', 'success')
    except Exception as e:
        flash(f'启动任务执行失败: {str(e)}', 'error')
    
    return redirect(url_for('account_detail', account_id=account_id))

@app.route('/account/<int:account_id>/delete', methods=['POST'])
def delete_account(account_id):
    """删除账号"""
    # 确认删除
    confirm = request.form.get('confirm')
    if confirm != 'yes':
        flash('请确认删除操作', 'error')
        return redirect(url_for('account_detail', account_id=account_id))
    
    success, message = manager.delete_account(account_id)
    flash(message, 'success' if success else 'error')
    
    if success:
        return redirect(url_for('index'))
    else:
        return redirect(url_for('account_detail', account_id=account_id))

@app.route('/api/account/<int:account_id>/invalid_links')
def api_account_invalid_links(account_id):
    """API: 获取账号的失效链接"""
    try:
        # 获取缓存中的失效链接信息
        invalid_links_summary = manager.get_invalid_links_summary(account_id)
        
        if invalid_links_summary and str(account_id) in invalid_links_summary:
            # 有缓存数据，直接返回
            result = invalid_links_summary[str(account_id)]
            result["cached"] = True
            return jsonify(result)
        else:
            # 没有缓存数据，返回空结果
            account = manager.get_account(account_id)
            if account:
                return jsonify({
                    "account_name": account.get("name"),
                    "account_index": account_id,
                    "invalid_links": [],
                    "total_tasks": len(account.get("tasklist", [])),
                    "invalid_count": 0,
                    "cached": False
                })
            else:
                return jsonify({"error": "账号不存在"}), 404
    except Exception as e:
        logger.error(f"获取失效链接失败: {e}")
        return jsonify({"error": f"获取失效链接失败: {str(e)}"}), 500

@app.route('/api/account/<int:account_id>/check_invalid_links', methods=['POST'])
def api_check_invalid_links(account_id):
    """API: 手动检查失效链接"""
    try:
        # 异步检查失效链接
        import asyncio
        
        async def check_links():
            return await manager.check_invalid_links(account_id)
        
        # 运行异步检查
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            invalid_links_by_account = loop.run_until_complete(check_links())
            if account_id in invalid_links_by_account:
                return jsonify(invalid_links_by_account[account_id])
            else:
                account = manager.get_account(account_id)
                return jsonify({
                    "account_name": account.get("name") if account else "未知账号",
                    "account_index": account_id,
                    "invalid_links": [],
                    "total_tasks": len(account.get("tasklist", [])) if account else 0,
                    "invalid_count": 0,
                    "cached": False
                })
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"检查失效链接失败: {e}")
        return jsonify({"error": f"检查失效链接失败: {str(e)}"}), 500


# ==================== 登录系统路由 ====================

@app.route('/simple_login', methods=['GET', 'POST'])
def simple_login():
    """简单登录页面"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # 验证用户名和密码
        if username in VALID_USERS and VALID_USERS[username] == password:
            session['logged_in'] = True
            session['username'] = username
            flash('登录成功！', 'success')
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误', 'error')
    
    # 如果用户已经登录，重定向到首页
    if 'logged_in' in session and session['logged_in']:
        return redirect(url_for('index'))
    
    return render_template('simple_login.html')

@app.route('/logout')
def logout():
    """退出登录"""
    session.pop('logged_in', None)
    session.pop('username', None)
    flash('已退出登录', 'success')
    return redirect(url_for('simple_login'))

# ==================== 模板文件 ====================

# 创建模板目录
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates')
if not os.path.exists(TEMPLATES_DIR):
    os.makedirs(TEMPLATES_DIR)

# 创建静态文件目录
STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
