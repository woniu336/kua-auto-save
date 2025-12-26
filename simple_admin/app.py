#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from flask import Flask, jsonify, request, render_template, send_from_directory, session, redirect, url_for, flash
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timedelta
import logging
import hashlib

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = "simple_quark_admin_secret_key_2025"
# 设置session有效期为48小时
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=48)

# 文件路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)

# 配置文件路径
CONFIG_FILE = os.path.join(PARENT_DIR, "quark_config.json")
LINKS_FILE = os.path.join(PARENT_DIR, "movie_links.txt")

# 全局变量存储运行状态
script_output = {"status": "idle", "output": "", "last_run": None}

# 用户数据文件路径
USERS_FILE = os.path.join(BASE_DIR, "users.json")

def hash_password(password):
    """使用SHA-256哈希密码"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def read_users():
    """读取用户数据"""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                users = json.load(f)
        else:
            # 创建默认用户 admin/admin123
            users = {
                "admin": {
                    "password": hash_password("admin123"),
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            }
            with open(USERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(users, f, indent=2, ensure_ascii=False)
        return users
    except Exception as e:
        logger.error(f"读取用户数据失败: {e}")
        return {}

def write_users(users):
    """写入用户数据"""
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"写入用户数据失败: {e}")
        return False

def login_required(f):
    """登录检查装饰器"""
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def read_config():
    """读取配置文件"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 确保配置中有cookies数组（新结构）
        if "cookies" not in config:
            # 从旧结构转换到新结构
            if "cookie" in config:
                cookies = config.get("cookie", [])
                if isinstance(cookies, str):
                    cookies = [cookies]
                
                config["cookies"] = []
                for i, cookie in enumerate(cookies):
                    config["cookies"].append({
                        "name": f"Cookie{i+1}",
                        "cookie": cookie,
                        "tasklist": config.get("tasklist", [])
                    })
                # 保留旧结构用于兼容性
            else:
                config["cookies"] = []
        
        return config
    except FileNotFoundError:
        # 创建默认配置
        default_config = {
            "cookies": [
                {
                    "name": "默认Cookie",
                    "cookie": "",
                    "tasklist": []
                }
            ],
            "push_config": {
                "QUARK_SIGN_NOTIFY": True,
                "DD_BOT_SECRET": "",
                "DD_BOT_TOKEN": "",
                "CONSOLE": True
            },
            "emby": {
                "url": "",
                "apikey": ""
            },
            "magic_regex": {
                "$TV": {
                    "pattern": ".*?(S\\d{1,2}E)?P?(\\d{1,3}).*?\\.(mp4|mkv)",
                    "replace": "\\1\\2.\\3"
                }
            },
            "crontab": "0 8,18,20 * * *"
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        return default_config
    except Exception as e:
        logger.error(f"读取配置文件失败: {e}")
        return {}

def write_config(config):
    """写入配置文件"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"写入配置文件失败: {e}")
        return False

def read_movie_links():
    """读取movie_links.txt文件"""
    try:
        with open(LINKS_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        links = []
        for i, line in enumerate(lines):
            line = line.strip()
            if line:
                parts = line.split('=')
                if len(parts) >= 3:
                    links.append({
                        "id": i,
                        "name": parts[0],
                        "url": parts[1],
                        "directory": parts[2],
                        "raw": line
                    })
        return links
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.error(f"读取movie_links.txt失败: {e}")
        return []

def write_movie_links(links):
    """写入movie_links.txt文件"""
    try:
        lines = []
        for link in links:
            lines.append(f"{link['name']}={link['url']}={link['directory']}")
        
        with open(LINKS_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return True
    except Exception as e:
        logger.error(f"写入movie_links.txt失败: {e}")
        return False

def run_script_async(script_name, cookie_index=None, args=""):
    """异步运行脚本"""
    global script_output
    
    def run():
        global script_output
        script_output["status"] = "running"
        script_output["output"] = ""
        script_output["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            if script_name == "movie_list.py":
                cmd = [sys.executable, os.path.join(PARENT_DIR, "movie_list.py")]
            elif script_name == "quark_auto_save.py":
                cmd = [sys.executable, os.path.join(PARENT_DIR, "quark_auto_save.py"), CONFIG_FILE]
                if cookie_index is not None:
                    cmd.append(str(cookie_index))
                if args:
                    cmd.append(args)
            else:
                script_output["output"] = f"未知脚本: {script_name}"
                script_output["status"] = "error"
                return
            
            # 设置环境变量，确保Python输出不被缓冲
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            env['PYTHONIOENCODING'] = 'utf-8'
            
            # 使用Popen实时捕获输出
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 将stderr合并到stdout
                text=True,
                encoding='utf-8',
                bufsize=1,  # 行缓冲
                universal_newlines=True,
                env=env
            )
            
            output_lines = []
            # 实时读取输出 - 使用迭代器逐行读取
            if process.stdout:
                for line in iter(process.stdout.readline, ''):
                    if line:
                        output_lines.append(line)
                        # 更新输出，让前端可以实时看到
                        script_output["output"] = ''.join(output_lines)
                        # 立即刷新Python的输出缓冲区
                        sys.stdout.flush()
            
            # 等待进程完成
            return_code = process.wait()
            
            if return_code == 0:
                script_output["status"] = "completed"
            else:
                script_output["status"] = "error"
                if not script_output["output"]:
                    script_output["output"] = f"脚本执行失败，返回码: {return_code}"
            
        except Exception as e:
            script_output["output"] = f"运行脚本时出错: {str(e)}"
            script_output["status"] = "error"
            logger.error(f"运行脚本异常: {e}")
    
    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()

@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    if 'username' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '')
        if username:
            username = username.strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('用户名和密码不能为空', 'danger')
            return render_template('login.html')
        
        users = read_users()
        if username in users and users[username]['password'] == hash_password(password):
            session['username'] = username
            session.permanent = True  # 启用永久session
            flash('登录成功', 'success')
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误', 'danger')
            return render_template('login.html')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """退出登录"""
    session.pop('username', None)
    flash('已退出登录', 'info')
    return redirect(url_for('login'))

@app.route('/change_password', methods=['POST'])
def change_password():
    """修改密码"""
    if 'username' not in session:
        return jsonify({"success": False, "message": "未登录"}), 401
    
    data = request.json
    if not data:
        return jsonify({"success": False, "message": "请求数据为空"}), 400
    
    # 支持两种字段名：current_password（前端使用）和 old_password（兼容性）
    current_password = data.get('current_password', '')
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    
    # 优先使用current_password，如果不存在则使用old_password
    password_to_check = current_password if current_password else old_password
    
    if not password_to_check or not new_password:
        return jsonify({"success": False, "message": "当前密码和新密码不能为空"}), 400
    
    username = session['username']
    users = read_users()
    
    if username not in users:
        return jsonify({"success": False, "message": "用户不存在"}), 404
    
    if users[username]['password'] != hash_password(password_to_check):
        return jsonify({"success": False, "message": "当前密码错误"}), 400
    
    users[username]['password'] = hash_password(new_password)
    
    if write_users(users):
        return jsonify({"success": True, "message": "密码修改成功"})
    else:
        return jsonify({"success": False, "message": "密码修改失败"}), 500

@app.route('/')
@login_required
def index():
    """主页面"""
    return render_template('index.html')

@app.route('/api/cookies', methods=['GET'])
@login_required
def get_cookies():
    """获取所有cookie"""
    config = read_config()
    cookies = config.get("cookies", [])
    return jsonify(cookies)

@app.route('/api/cookies', methods=['POST'])
@login_required
def add_cookie():
    """添加新的cookie"""
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "message": "请求数据为空"}), 400
            
        name = data.get('name', '')
        cookie = data.get('cookie', '')
        
        if not name or not cookie:
            return jsonify({"success": False, "message": "名称和cookie值不能为空"}), 400
        
        config = read_config()
        cookies = config.get("cookies", [])
        
        # 检查名称是否已存在
        for existing_cookie in cookies:
            if existing_cookie.get('name') == name:
                return jsonify({"success": False, "message": "名称已存在"}), 400
        
        new_cookie = {
            "name": name,
            "cookie": cookie,
            "tasklist": []
        }
        
        cookies.append(new_cookie)
        config["cookies"] = cookies
        
        if write_config(config):
            return jsonify({"success": True, "message": "Cookie添加成功", "cookie": new_cookie})
        else:
            return jsonify({"success": False, "message": "配置写入失败"}), 500
    except Exception as e:
        logger.error(f"添加cookie失败: {e}")
        return jsonify({"success": False, "message": f"添加cookie失败: {str(e)}"}), 500

@app.route('/api/cookies/<int:cookie_index>', methods=['PUT'])
@login_required
def update_cookie(cookie_index):
    """更新cookie"""
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "message": "请求数据为空"}), 400
            
        config = read_config()
        cookies = config.get("cookies", [])
        
        if cookie_index < 0 or cookie_index >= len(cookies):
            return jsonify({"success": False, "message": "Cookie索引无效"}), 404
        
        name = data.get('name', cookies[cookie_index].get('name'))
        cookie = data.get('cookie', cookies[cookie_index].get('cookie'))
        
        # 检查名称是否与其他cookie冲突
        for i, existing_cookie in enumerate(cookies):
            if i != cookie_index and existing_cookie.get('name') == name:
                return jsonify({"success": False, "message": "名称已存在"}), 400
        
        # 更新通知配置
        dd_bot_token = data.get('dd_bot_token', cookies[cookie_index].get('dd_bot_token', ''))
        dd_bot_secret = data.get('dd_bot_secret', cookies[cookie_index].get('dd_bot_secret', ''))
        tg_bot_token = data.get('tg_bot_token', cookies[cookie_index].get('tg_bot_token', ''))
        tg_user_id = data.get('tg_user_id', cookies[cookie_index].get('tg_user_id', ''))
        
        # 更新定时任务配置
        crontab = data.get('crontab', cookies[cookie_index].get('crontab', ''))
        
        cookies[cookie_index]['name'] = name
        cookies[cookie_index]['cookie'] = cookie
        cookies[cookie_index]['dd_bot_token'] = dd_bot_token
        cookies[cookie_index]['dd_bot_secret'] = dd_bot_secret
        cookies[cookie_index]['tg_bot_token'] = tg_bot_token
        cookies[cookie_index]['tg_user_id'] = tg_user_id
        cookies[cookie_index]['crontab'] = crontab
        
        # 确保tasklist字段存在
        if 'tasklist' not in cookies[cookie_index]:
            cookies[cookie_index]['tasklist'] = []
        
        config["cookies"] = cookies
        
        if write_config(config):
            return jsonify({"success": True, "message": "Cookie更新成功", "cookie": cookies[cookie_index]})
        else:
            return jsonify({"success": False, "message": "配置写入失败"}), 500
    except Exception as e:
        logger.error(f"更新cookie失败: {e}")
        return jsonify({"success": False, "message": f"更新cookie失败: {str(e)}"}), 500

@app.route('/api/cookies/<int:cookie_index>', methods=['DELETE'])
@login_required
def delete_cookie(cookie_index):
    """删除cookie"""
    try:
        config = read_config()
        cookies = config.get("cookies", [])
        
        if cookie_index < 0 or cookie_index >= len(cookies):
            return jsonify({"success": False, "message": "Cookie索引无效"}), 404
        
        deleted_cookie = cookies.pop(cookie_index)
        config["cookies"] = cookies
        
        if write_config(config):
            return jsonify({"success": True, "message": "Cookie删除成功", "cookie": deleted_cookie})
        else:
            return jsonify({"success": False, "message": "配置写入失败"}), 500
    except Exception as e:
        logger.error(f"删除cookie失败: {e}")
        return jsonify({"success": False, "message": f"删除cookie失败: {str(e)}"}), 500

@app.route('/api/cookies/<int:cookie_index>/tasklist', methods=['GET'])
@login_required
def get_cookie_tasklist(cookie_index):
    """获取指定cookie的tasklist（支持分页）"""
    try:
        # 获取分页参数，确保转换为整数
        page_str = request.args.get('page', '1')
        per_page_str = request.args.get('per_page', '25')
        
        try:
            page = int(page_str)
        except ValueError:
            page = 1
            
        try:
            per_page = int(per_page_str)
        except ValueError:
            per_page = 25
        
        config = read_config()
        cookies = config.get("cookies", [])
        
        if cookie_index < 0 or cookie_index >= len(cookies):
            return jsonify({"success": False, "message": "Cookie索引无效"}), 404
        
        tasklist = cookies[cookie_index].get("tasklist", [])
        
        # 计算分页
        total_tasks = len(tasklist)
        if per_page <= 0:
            per_page = 25  # 防止除零错误
        total_pages = (total_tasks + per_page - 1) // per_page if total_tasks > 0 else 1  # 向上取整
        
        # 确保页码在有效范围内
        if page < 1:
            page = 1
        elif page > total_pages and total_pages > 0:
            page = total_pages
        
        # 计算起始和结束索引
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        
        # 获取当前页的数据
        paginated_tasks = tasklist[start_idx:end_idx]
        
        # 计算有效和失效任务数量
        # 实际检查任务有效性
        valid_count = 0
        invalid_count = 0
        
        # 导入必要的模块
        import sys
        import os
        import asyncio
        import aiohttp
        
        # 添加父目录到路径
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, parent_dir)
        
        try:
            from quark_auto_save import Quark
        except ImportError:
            logger.error("无法导入Quark类")
            # 如果无法导入Quark类，返回假设所有任务都有效
            valid_count = total_tasks
            invalid_count = 0
        else:
            # 获取cookie值
            cookie_data = cookies[cookie_index]
            cookie_value = cookie_data.get("cookie", "")
            
            if not cookie_value:
                logger.error("Cookie值为空")
                valid_count = total_tasks
                invalid_count = 0
            else:
                # 创建Quark对象
                quark = Quark(cookie_value, cookie_index)
                
                async def check_task_validity(task):
                    """检查单个任务的有效性"""
                    try:
                        shareurl = task.get("shareurl", "")
                        if not shareurl:
                            return False
                        
                        # 获取链接ID
                        result = quark.get_id_from_url(shareurl)
                        if result is None:
                            return False
                        
                        pwd_id, _ = result
                        
                        # 检查stoken - 对于公开分享链接，不需要账号初始化
                        async with aiohttp.ClientSession() as session:
                            # 直接检查链接有效性，不进行账号初始化
                            # 因为公开分享的链接不需要有效Cookie
                            is_valid, message = await quark.get_stoken(session, pwd_id)
                            return is_valid
                    except Exception as e:
                        logger.error(f"检查任务有效性失败: {e}")
                        return False
                
                async def check_all_tasks():
                    """检查所有任务的有效性"""
                    tasks_to_check = []
                    for task in tasklist:
                        tasks_to_check.append(check_task_validity(task))
                    
                    # 批量检查所有任务
                    results = await asyncio.gather(*tasks_to_check, return_exceptions=True)
                    
                    valid = 0
                    invalid = 0
                    for result in results:
                        if isinstance(result, Exception):
                            logger.error(f"任务检查异常: {result}")
                            invalid += 1
                        elif result:
                            valid += 1
                        else:
                            invalid += 1
                    
                    return valid, invalid
                
                # 运行异步检查
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    valid_count, invalid_count = loop.run_until_complete(check_all_tasks())
                    loop.close()
                except Exception as e:
                    logger.error(f"运行异步检查失败: {e}")
                    # 如果异步检查失败，返回假设所有任务都有效
                    valid_count = total_tasks
                    invalid_count = 0
        
        return jsonify({
            "success": True,
            "tasks": paginated_tasks,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total_tasks": total_tasks,
                "total_pages": total_pages,
                "has_prev": page > 1,
                "has_next": page < total_pages
            },
            "counts": {
                "valid": valid_count,
                "invalid": invalid_count
            }
        })
    except Exception as e:
        logger.error(f"获取tasklist失败: {e}")
        return jsonify({"success": False, "message": f"获取tasklist失败: {str(e)}"}), 500

@app.route('/api/cookies/<int:cookie_index>/tasklist', methods=['POST'])
@login_required
def update_cookie_tasklist(cookie_index):
    """更新指定cookie的tasklist"""
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "message": "请求数据为空"}), 400
            
        tasklist = data.get('tasklist', [])
        
        if not isinstance(tasklist, list):
            return jsonify({"success": False, "message": "tasklist必须是数组"}), 400
        
        config = read_config()
        cookies = config.get("cookies", [])
        
        if cookie_index < 0 or cookie_index >= len(cookies):
            return jsonify({"success": False, "message": "Cookie索引无效"}), 404
        
        cookies[cookie_index]["tasklist"] = tasklist
        config["cookies"] = cookies
        
        if write_config(config):
            return jsonify({"success": True, "message": "Tasklist更新成功"})
        else:
            return jsonify({"success": False, "message": "配置写入失败"}), 500
    except Exception as e:
        logger.error(f"更新tasklist失败: {e}")
        return jsonify({"success": False, "message": f"更新tasklist失败: {str(e)}"}), 500
@app.route('/api/links', methods=['GET'])
@login_required
def get_links():
    """获取转存链接列表"""
    cookie_index = request.args.get('cookie_index', type=int, default=None)
    links = read_movie_links()
    
    # 如果指定了cookie_index，只返回该cookie的tasklist中的链接
    if cookie_index is not None:
        config = read_config()
        cookies = config.get("cookies", [])
        if 0 <= cookie_index < len(cookies):
            cookie_tasklist = cookies[cookie_index].get("tasklist", [])
            # 过滤链接，只返回在tasklist中的
            filtered_links = []
            for link in links:
                if link['raw'] in cookie_tasklist:
                    filtered_links.append(link)
            return jsonify(filtered_links)
    
    return jsonify(links)

@app.route('/api/links', methods=['POST'])
@login_required
def add_link():
    """添加转存链接"""
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "message": "请求数据为空"}), 400
            
        name = data.get('name', '')
        url = data.get('url', '')
        directory = data.get('directory', '')
        
        if not name or not url or not directory:
            return jsonify({"success": False, "message": "名称、链接和目录不能为空"}), 400
        
        links = read_movie_links()
        
        # 生成新ID
        new_id = max([link['id'] for link in links], default=-1) + 1
        
        new_link = {
            "id": new_id,
            "name": name,
            "url": url,
            "directory": directory,
            "raw": f"{name}={url}={directory}"
        }
        
        links.append(new_link)
        
        if write_movie_links(links):
            return jsonify({"success": True, "message": "链接添加成功", "link": new_link})
        else:
            return jsonify({"success": False, "message": "链接写入失败"}), 500
    except Exception as e:
        logger.error(f"添加链接失败: {e}")
        return jsonify({"success": False, "message": f"添加链接失败: {str(e)}"}), 500

@app.route('/api/links/<int:link_id>', methods=['PUT'])
@login_required
def update_link(link_id):
    """更新转存链接"""
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "message": "请求数据为空"}), 400
            
        links = read_movie_links()
        
        for i, link in enumerate(links):
            if link['id'] == link_id:
                name = data.get('name', link['name'])
                url = data.get('url', link['url'])
                directory = data.get('directory', link['directory'])
                
                links[i]['name'] = name
                links[i]['url'] = url
                links[i]['directory'] = directory
                links[i]['raw'] = f"{name}={url}={directory}"
                
                if write_movie_links(links):
                    return jsonify({"success": True, "message": "链接更新成功", "link": links[i]})
                else:
                    return jsonify({"success": False, "message": "链接写入失败"}), 500
        
        return jsonify({"success": False, "message": "链接不存在"}), 404
    except Exception as e:
        logger.error(f"更新链接失败: {e}")
        return jsonify({"success": False, "message": f"更新链接失败: {str(e)}"}), 500

@app.route('/api/links/<int:link_id>', methods=['DELETE'])
@login_required
def delete_link(link_id):
    """删除转存链接"""
    try:
        links = read_movie_links()
        new_links = [link for link in links if link['id'] != link_id]
        
        if len(new_links) == len(links):
            return jsonify({"success": False, "message": "链接不存在"}), 404
        
        if write_movie_links(new_links):
            return jsonify({"success": True, "message": "链接删除成功"})
        else:
            return jsonify({"success": False, "message": "链接写入失败"}), 500
    except Exception as e:
        logger.error(f"删除链接失败: {e}")
        return jsonify({"success": False, "message": f"删除链接失败: {str(e)}"}), 500

@app.route('/api/script/status', methods=['GET'])
@login_required
def get_script_status():
    """获取脚本运行状态"""
    global script_output
    return jsonify(script_output)

@app.route('/api/script/run', methods=['POST'])
@login_required
def run_script():
    """运行脚本"""
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "message": "请求数据为空"}), 400
            
        script_name = data.get('script', '')
        args = data.get('args', '')
        cookie_index = data.get('cookie_index', None)
        
        if script_name not in ['movie_list.py', 'quark_auto_save.py']:
            return jsonify({"success": False, "message": "无效的脚本名称"}), 400
        
        run_script_async(script_name, cookie_index, args)
        return jsonify({"success": True, "message": "脚本已开始运行"})
    except Exception as e:
        logger.error(f"运行脚本失败: {e}")
        return jsonify({"success": False, "message": f"运行脚本失败: {str(e)}"}), 500

@app.route('/api/crontab', methods=['GET'])
@login_required
def get_crontab():
    """获取定时任务配置"""
    config = read_config()
    crontab = config.get('crontab', '0 8,18,20 * * *')
    return jsonify({"crontab": crontab})

@app.route('/api/crontab', methods=['POST'])
@login_required
def update_crontab():
    """更新定时任务配置"""
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "message": "请求数据为空"}), 400
            
        crontab = data.get('crontab', '')
        
        if not crontab:
            return jsonify({"success": False, "message": "定时任务表达式不能为空"}), 400
        
        config = read_config()
        config['crontab'] = crontab
        
        if write_config(config):
            return jsonify({"success": True, "message": "定时任务更新成功"})
        else:
            return jsonify({"success": False, "message": "定时任务写入失败"}), 500
    except Exception as e:
        logger.error(f"更新定时任务失败: {e}")
        return jsonify({"success": False, "message": f"更新定时任务失败: {str(e)}"}), 500

@app.route('/api/check_link_validity', methods=['POST'])
@login_required
def check_link_validity():
    """检查分享链接有效性"""
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "message": "请求数据为空"}), 400
            
        cookie_index = data.get('cookie_index')
        shareurl = data.get('shareurl', '')
        
        if cookie_index is None:
            return jsonify({"success": False, "message": "cookie_index不能为空"}), 400
            
        if not shareurl:
            return jsonify({"success": False, "message": "分享链接不能为空"}), 400
        
        config = read_config()
        cookies = config.get("cookies", [])
        
        if cookie_index < 0 or cookie_index >= len(cookies):
            return jsonify({"success": False, "message": "Cookie索引无效"}), 404
        
        cookie_data = cookies[cookie_index]
        cookie_value = cookie_data.get("cookie", "")
        
        if not cookie_value:
            return jsonify({"success": False, "message": "Cookie值为空"}), 400
        
        # 导入Quark类
        import sys
        import os
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, parent_dir)
        
        try:
            from quark_auto_save import Quark
        except ImportError:
            return jsonify({"success": False, "message": "无法导入Quark类"}), 500
        
        # 创建Quark对象
        quark = Quark(cookie_value, cookie_index)
        
        # 检查链接有效性
        import asyncio
        import aiohttp
        
        async def check_validity():
            async with aiohttp.ClientSession() as session:
                # 直接检查链接有效性，不进行账号初始化
                # 因为公开分享的链接是公开的，和cookie无关
                
                # 获取链接ID
                result = quark.get_id_from_url(shareurl)
                if result is None:
                    return False, "链接格式无效"
                
                pwd_id, _ = result
                
                # 检查stoken - 对于公开分享链接，不需要账号初始化
                is_valid, message = await quark.get_stoken(session, pwd_id)
                return is_valid, message
        
        # 运行异步检查
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            is_valid, message = loop.run_until_complete(check_validity())
            return jsonify({
                "success": True,
                "is_valid": is_valid,
                "message": message
            })
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"检查链接有效性失败: {e}")
        return jsonify({"success": False, "message": f"检查链接有效性失败: {str(e)}"}), 500

@app.route('/api/validate_cookie', methods=['POST'])
@login_required
def validate_cookie():
    """验证Cookie有效性"""
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "message": "请求数据为空"}), 400
            
        cookie_value = data.get('cookie', '')
        
        if not cookie_value:
            return jsonify({"success": False, "message": "Cookie值不能为空"}), 400
        
        # 导入Quark类
        import sys
        import os
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, parent_dir)
        
        try:
            from quark_auto_save import Quark
        except ImportError:
            return jsonify({"success": False, "message": "无法导入Quark类"}), 500
        
        # 创建Quark对象，使用临时索引0
        quark = Quark(cookie_value, 0)
        
        # 检查Cookie有效性
        import asyncio
        import aiohttp
        
        async def check_cookie_validity():
            async with aiohttp.ClientSession() as session:
                try:
                    # 尝试初始化账号来验证Cookie
                    account_info = await quark.init(session)
                    if account_info:
                        return True, f"Cookie有效，账号昵称: {account_info.get('nickname', '未知')}"
                    else:
                        return False, "Cookie无效，无法获取账号信息"
                except Exception as e:
                    return False, f"验证Cookie时出错: {str(e)}"
        
        # 运行异步检查
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            is_valid, message = loop.run_until_complete(check_cookie_validity())
            return jsonify({
                "success": True,
                "is_valid": is_valid,
                "message": message
            })
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"验证Cookie失败: {e}")
        return jsonify({"success": False, "message": f"验证Cookie失败: {str(e)}"}), 500

@app.route('/static/<path:filename>')
def serve_static(filename):
    """提供静态文件"""
    return send_from_directory('static', filename)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5006)
