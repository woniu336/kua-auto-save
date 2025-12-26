#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Modify: 2024-04-03
# Repo: https://github.com/Cp0204/quark_auto_save
# ConfigFile: quark_config.json

import os
import re
import sys
import json
import time
import random
import asyncio
import aiohttp
import logging
from datetime import datetime
from functools import lru_cache
from typing import Dict, List, Any, Optional, Tuple, Union

# 兼容青龙
try:
    from treelib.tree import Tree
except ImportError:
    os.system("pip3 install treelib aiohttp &> /dev/null")
    from treelib.tree import Tree

CONFIG_DATA: Dict[str, Any] = {}
NOTIFYS: List[str] = []
GH_PROXY = os.environ.get("GH_PROXY", "https://ghproxy.net/")

MAGIC_REGEX: Dict[str, Dict[str, str]] = {
    "$TV": {
        "pattern": ".*?(S\\d{1,2}E)?P?(\\d{1,3}).*?\\.(mp4|mkv)",
        "replace": "\\1\\2.\\3",
    },
}

# 设置日志配置
logger = logging.getLogger('QuarkAutoSave')
logger.setLevel(logging.DEBUG)

# 创建文件处理器
file_handler = logging.FileHandler('quark_save.log', mode='a', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)

# 创建终端处理器
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
stream_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stream_handler.setFormatter(stream_formatter)

# 将处理器添加到日志记录器
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

async def fetch(session: aiohttp.ClientSession, method: str, url: str, **kwargs) -> Optional[Dict[str, Any]]:
    try:
        async with session.request(method, url, **kwargs) as response:
            response.raise_for_status()
            try:
                return await response.json()
            except aiohttp.ContentTypeError:
                # 如果响应不是JSON，尝试读取原始文本
                text = await response.text()
                logger.error(f"响应不是JSON格式: {method} {url} - 响应内容: {text[:200]}")
                # 尝试解析为JSON，即使Content-Type不正确
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    # 如果仍然无法解析为JSON，返回包含错误信息的字典
                    return {
                        "code": -1,
                        "message": f"响应不是有效的JSON格式: {text[:100]}...",
                        "raw_response": text[:500]
                    }
            except json.JSONDecodeError as e:
                text = await response.text()
                logger.error(f"JSON解析错误: {method} {url} - 错误: {e} - 响应内容: {text[:200]}")
                # 尝试修复常见的JSON格式问题
                try:
                    # 尝试修复可能的JSON格式问题
                    fixed_text = text.strip()
                    if not fixed_text.startswith('{') and not fixed_text.startswith('['):
                        # 如果不是以{或[开头，尝试包装它
                        # 转义字符串中的特殊字符
                        import json as json_module
                        escaped_text = json_module.dumps(fixed_text)
                        fixed_text = f'{{"data": {escaped_text}}}'
                    return json.loads(fixed_text)
                except json.JSONDecodeError:
                    return {
                        "code": -1,
                        "message": f"JSON解析失败: {str(e)}",
                        "raw_response": text[:500]
                    }
    except aiohttp.ClientResponseError as e:
        # 简化错误处理，不再检查fr参数切换
        url_str = str(url)
        # 如果URL是URL对象，提取实际的URL字符串
        import re
        url_match = re.search(r"URL\('([^']+)'\)", url_str)
        if url_match:
            url_str = url_match.group(1)
        
        logger.error(f"请求失败: {method} {url_str} - {e}")
        return {
            "code": e.status,
            "message": f"请求失败: {method} {url_str} - {e}",
            "status": e.status
        }
    except Exception as e:
        logger.error(f"请求失败: {method} {url} - {e}")
        # 对于非ClientResponseError异常，返回一个包含错误信息的字典
        return {
            "code": -1,
            "message": f"请求失败: {method} {url} - {e}",
            "status": -1
        }

def magic_regex_func(pattern: str, replace: str) -> Tuple[str, str]:
    keyword = pattern
    # 检查CONFIG_DATA是否已初始化并且包含magic_regex
    if CONFIG_DATA and "magic_regex" in CONFIG_DATA and keyword in CONFIG_DATA["magic_regex"]:
        pattern = CONFIG_DATA["magic_regex"][keyword]["pattern"]
        if replace == "":
            replace = CONFIG_DATA["magic_regex"][keyword]["replace"]
    return pattern, replace

def send_ql_notify(title: str, body: str, cookie_index: Optional[int] = None) -> None:
    try:
        import notify
        
        # 从所有Cookie中查找有效的钉钉通知配置
        dd_bot_token: Optional[str] = None
        dd_bot_secret: Optional[str] = None
        
        # 从所有Cookie中查找有效的TG通知配置
        tg_bot_token: Optional[str] = None
        tg_user_id: Optional[str] = None
        
        if CONFIG_DATA.get("cookies"):
            # 如果指定了cookie_index，使用该索引对应的cookie配置
            if cookie_index is not None and 0 <= cookie_index < len(CONFIG_DATA["cookies"]):
                cookie_config = CONFIG_DATA["cookies"][cookie_index]
                # 查找钉钉配置
                token = cookie_config.get("dd_bot_token")
                secret = cookie_config.get("dd_bot_secret")
                if token and secret:
                    dd_bot_token = token
                    dd_bot_secret = secret
                
                # 查找TG配置
                tg_token = cookie_config.get("tg_bot_token")
                tg_id = cookie_config.get("tg_user_id")
                if tg_token and tg_id:
                    tg_bot_token = tg_token
                    tg_user_id = tg_id
                else:
                    # 如果没有找到当前cookie的配置，回退到遍历所有cookie
                    for cookie_config in CONFIG_DATA["cookies"]:
                        # 查找钉钉配置
                        token = cookie_config.get("dd_bot_token")
                        secret = cookie_config.get("dd_bot_secret")
                        if token and secret:
                            dd_bot_token = token
                            dd_bot_secret = secret
                        
                        # 查找TG配置
                        tg_token = cookie_config.get("tg_bot_token")
                        tg_id = cookie_config.get("tg_user_id")
                        if tg_token and tg_id:
                            tg_bot_token = tg_token
                            tg_user_id = tg_id
            else:
                # 如果没有指定cookie_index，遍历所有cookie（保持向后兼容）
                for cookie_config in CONFIG_DATA["cookies"]:
                    # 查找钉钉配置
                    token = cookie_config.get("dd_bot_token")
                    secret = cookie_config.get("dd_bot_secret")
                    if token and secret:
                        dd_bot_token = token
                        dd_bot_secret = secret
                    
                    # 查找TG配置
                    tg_token = cookie_config.get("tg_bot_token")
                    tg_id = cookie_config.get("tg_user_id")
                    if tg_token and tg_id:
                        tg_bot_token = tg_token
                        tg_user_id = tg_id
        
        # 如果找到了钉钉配置，发送钉钉通知
        if dd_bot_token and dd_bot_secret:
            # 使用ignore_default_config=True确保只发送钉钉通知
            notify.send(
                title, 
                body, 
                ignore_default_config=True,
                DD_BOT_TOKEN=dd_bot_token,
                DD_BOT_SECRET=dd_bot_secret,
                CONSOLE=True,
                HITOKOTO=False
            )
            logger.info("钉钉通知发送成功")
        else:
            logger.info("未找到有效的钉钉通知配置，跳过钉钉推送")
        
        # 如果找到了TG配置，发送TG通知
        if tg_bot_token and tg_user_id:
            # 使用ignore_default_config=True确保只发送TG通知
            notify.send(
                title, 
                body, 
                ignore_default_config=True,
                TG_BOT_TOKEN=tg_bot_token,
                TG_USER_ID=tg_user_id,
                CONSOLE=True,
                HITOKOTO=False
            )
            logger.info("TG通知发送成功")
        else:
            logger.info("未找到有效的TG通知配置，跳过TG推送")
            
    except Exception as e:
        logger.error(f"发送通知消息失败: {e}")

def add_notify(text: str) -> str:
    global NOTIFYS
    NOTIFYS.append(text)
    logger.info(text)
    return text

def download_file_sync(url: str, save_path: str) -> bool:
    try:
        import requests
        response = requests.get(url)
        if response.status_code == 200:
            with open(save_path, "wb") as file:
                file.write(response.content)
            return True
        else:
            logger.error(f"下载文件失败: {url} - 状态码 {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"下载文件异常: {url} - {e}")
        return False

def get_cookies(cookie_val: Union[str, List[str], None]) -> Union[List[str], bool]:
    if isinstance(cookie_val, list):
        return cookie_val
    elif cookie_val:
        if "\n" in cookie_val:
            return cookie_val.split("\n")
        else:
            return [cookie_val]
    else:
        return False

class Quark:
    def __init__(self, cookie: str, index: Optional[int] = None):
        self.cookie = cookie.strip()
        self.index = index + 1
        self.is_active = False
        self.nickname = ""
        self.st = self.match_st_form_cookie(cookie)
        self.mparam = self.match_mparam_form_cookie(cookie)
        self.savepath_fid = {"/": "0"}

    def match_st_form_cookie(self, cookie: str) -> str:
        # 修复正则表达式：匹配 =stxxxxxx; 格式
        # 支持多种格式：=stxxxxxx; 或 =stxxxxxx（没有分号）
        # 夸克Cookie中st参数通常以 =stxxxxxx 形式出现
        match = re.search(r"=st([a-zA-Z0-9]+)[;]?", cookie)
        return match.group(1) if match else ""

    def match_mparam_form_cookie(self, cookie: str) -> Dict[str, str]:
        mparam = {}
        kps_match = re.search(r"(?<!\w)kps=([a-zA-Z0-9%]+)[;&]?", cookie)
        sign_match = re.search(r"(?<!\w)sign=([a-zA-Z0-9%]+)[;&]?", cookie)
        vcode_match = re.search(r"(?<!\w)vcode=([a-zA-Z0-9%]+)[;&]?", cookie)
        if kps_match and sign_match and vcode_match:
            mparam = {
                "kps": kps_match.group(1).replace("%25", "%"),
                "sign": sign_match.group(1).replace("%25", "%"),
                "vcode": vcode_match.group(1).replace("%25", "%"),
            }
        return mparam

    def common_headers(self) -> Dict[str, str]:
        headers = {
            "cookie": self.cookie,
            "content-type": "application/json",
        }
        if self.st:  # self.st 现在是字符串，空字符串为 False
            headers["x-clouddrive-st"] = self.st
        return headers

    async def init(self, session: aiohttp.ClientSession) -> Union[Dict[str, Any], bool]:
        account_info = await self.get_account_info(session)
        if account_info:
            self.is_active = True
            self.nickname = account_info["nickname"]
            return account_info
        else:
            return False

    async def get_account_info(self, session: aiohttp.ClientSession) -> Union[Dict[str, Any], bool]:
        url = "https://pan.quark.cn/account/info"
        querystring = {"fr": "pc", "platform": "pc"}
        headers = self.common_headers()
        response = await fetch(session, "GET", url, headers=headers, params=querystring)
        if response and response.get("data"):
            return response["data"]
        else:
            return False

    async def get_growth_info(self, session: aiohttp.ClientSession) -> Union[Dict[str, Any], bool]:
        url = "https://drive-pc.quark.cn/1/clouddrive/capacity/growth/info"
        querystring = {
            "pr": "ucpro",
            "fr": "android",
            "kps": self.mparam.get("kps"),
            "sign": self.mparam.get("sign"),
            "vcode": self.mparam.get("vcode"),
        }
        headers = {
            "content-type": "application/json",
        }
        response = await fetch(session, "GET", url, headers=headers, params=querystring)
        if response and response.get("data"):
            return response["data"]
        else:
            return False

    async def get_growth_sign(self, session: aiohttp.ClientSession) -> Tuple[bool, Union[int, str]]:
        url = "https://drive-pc.quark.cn/1/clouddrive/capacity/growth/sign"
        querystring = {
            "pr": "ucpro",
            "fr": "android",
            "kps": self.mparam.get("kps"),
            "sign": self.mparam.get("sign"),
            "vcode": self.mparam.get("vcode"),
        }
        payload = {
            "sign_cyclic": True,
        }
        headers = {
            "content-type": "application/json",
        }
        response = await fetch(session, "POST", url, json=payload, headers=headers, params=querystring)
        if response and response.get("data"):
            return True, response["data"]["sign_daily_reward"]
        elif response:
            return False, response["message"]
        else:
            return False, "未知错误"

    def get_id_from_url(self, url: str) -> Union[Tuple[str, str], None]:
        url = url.replace("https://pan.quark.cn/s/", "")
        pattern = r"(\w+)(#/list/share.*/(\w+))?"
        match = re.search(pattern, url)
        if match:
            pwd_id = match.group(1)
            if match.group(2):
                pdir_fid = match.group(3)
            else:
                pdir_fid = "0"
            return pwd_id, pdir_fid
        else:
            return None

    async def get_stoken(self, session: aiohttp.ClientSession, pwd_id: str) -> Tuple[bool, str]:
        url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token"
        querystring = {"pr": "ucpro", "fr": "pc"}
        payload = {"pwd_id": pwd_id, "passcode": ""}
        headers = self.common_headers()
        response = await fetch(session, "POST", url, json=payload, headers=headers, params=querystring)
        if response:
            if response.get("data"):
                return True, response["data"]["stoken"]
            elif response.get("message"):
                # 确保消息是字符串且不包含可能破坏JSON的字符
                message = str(response["message"])
                # 移除可能破坏JSON的特殊字符
                message = message.replace('"', "'").replace('\n', ' ').replace('\r', ' ')
                return False, message
            elif response.get("code") == -1:
                # fetch函数返回的非JSON响应
                raw_response = response.get("raw_response", "")
                if raw_response:
                    # 截取前100个字符，避免过长
                    return False, f"API返回非JSON响应: {raw_response[:100]}..."
                else:
                    return False, "API返回非JSON响应"
            else:
                return False, "未知API响应格式"
        else:
            return False, "请求失败或无响应"

    async def get_detail(self, session: aiohttp.ClientSession, pwd_id: str, stoken: str, pdir_fid: str) -> List[Dict[str, Any]]:
        file_list = []
        page = 1
        while True:
            url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail"
            querystring = {
                "pr": "ucpro",
                "fr": "pc",
                "pwd_id": pwd_id,
                "stoken": stoken,
                "pdir_fid": pdir_fid,
                "force": "0",
                "_page": page,
                "_size": "50",
                "_fetch_banner": "0",
                "_fetch_share": "0",
                "_fetch_total": "1",
                "_sort": "file_type:asc,updated_at:desc",
            }
            headers = self.common_headers()
            response = await fetch(session, "GET", url, headers=headers, params=querystring)
            if response and response["data"]["list"]:
                file_list += response["data"]["list"]
                page += 1
            else:
                break
            if len(file_list) >= response["metadata"]["_total"]:
                break
        return file_list

    async def get_fids(self, session: aiohttp.ClientSession, file_paths: Tuple[str, ...]) -> List[Dict[str, Any]]:
        # 使用实例级别的缓存，避免协程重用问题
        cache_key = tuple(file_paths)
        if not hasattr(self, '_fids_cache'):
            self._fids_cache = {}
        
        if cache_key in self._fids_cache:
            return self._fids_cache[cache_key]
        
        fids = []
        while file_paths:
            batch = file_paths[:50]
            file_paths = file_paths[50:]
            url = "https://drive-pc.quark.cn/1/clouddrive/file/info/path_list"
            querystring = {"pr": "ucpro", "fr": "pc"}
            payload = {"file_path": batch, "namespace": "0"}
            headers = self.common_headers()
            response = await fetch(session, "POST", url, json=payload, headers=headers, params=querystring)
            if response and response["code"] == 0:
                fids += response["data"]
            else:
                logger.error(f"获取目录ID失败: {response['message'] if response else '无响应'}")
                break
        
        # 缓存结果
        self._fids_cache[cache_key] = fids
        return fids

    async def ls_dir(self, session: aiohttp.ClientSession, pdir_fid: str) -> List[Dict[str, Any]]:
        file_list = []
        page = 1
        while True:
            url = "https://drive-pc.quark.cn/1/clouddrive/file/sort"
            querystring = {
                "pr": "ucpro",
                "fr": "pc",
                "uc_param_str": "",
                "pdir_fid": pdir_fid,
                "_page": page,
                "_size": "50",
                "_fetch_total": "1",
                "_fetch_sub_dirs": "0",
                "_sort": "file_type:asc,updated_at:desc",
            }
            headers = self.common_headers()
            response = await fetch(session, "GET", url, headers=headers, params=querystring)
            if response and response["data"]["list"]:
                file_list += response["data"]["list"]
                page += 1
            else:
                break
            if len(file_list) >= response["metadata"]["_total"]:
                break
        return file_list

    async def save_file(self, session: aiohttp.ClientSession, fid_list: List[str], fid_token_list: List[str], to_pdir_fid: str, pwd_id: str, stoken: str) -> Optional[Dict[str, Any]]:
        url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/save"
        querystring = {
            "pr": "ucpro",
            "fr": "pc",
            "uc_param_str": "",
            "app": "clouddrive",
            "__dt": int(random.uniform(1, 5) * 60 * 1000),
            "__t": datetime.now().timestamp(),
        }
        payload = {
            "fid_list": fid_list,
            "fid_token_list": fid_token_list,
            "to_pdir_fid": to_pdir_fid,
            "pwd_id": pwd_id,
            "stoken": stoken,
            "pdir_fid": "0",
            "scene": "link",
        }
        headers = self.common_headers()
        response = await fetch(session, "POST", url, json=payload, headers=headers, params=querystring)
        return response

    async def mkdir(self, session: aiohttp.ClientSession, dir_path: str) -> Optional[Dict[str, Any]]:
        url = "https://drive-pc.quark.cn/1/clouddrive/file"
        querystring = {"pr": "ucpro", "fr": "pc", "uc_param_str": ""}
        payload = {
            "pdir_fid": "0",
            "file_name": "",
            "dir_path": dir_path,
            "dir_init_lock": False,
        }
        headers = self.common_headers()
        response = await fetch(session, "POST", url, json=payload, headers=headers, params=querystring)
        return response

    async def rename(self, session: aiohttp.ClientSession, fid: str, file_name: str) -> Optional[Dict[str, Any]]:
        url = "https://drive-pc.quark.cn/1/clouddrive/file/rename"
        querystring = {"pr": "ucpro", "fr": "pc", "uc_param_str": ""}
        payload = {"fid": fid, "file_name": file_name}
        headers = self.common_headers()
        response = await fetch(session, "POST", url, json=payload, headers=headers, params=querystring)
        return response

    async def delete(self, session: aiohttp.ClientSession, filelist: List[str]) -> Optional[Dict[str, Any]]:
        url = "https://drive-pc.quark.cn/1/clouddrive/file/delete"
        querystring = {"pr": "ucpro", "fr": "pc", "uc_param_str": ""}
        payload = {"action_type": 2, "filelist": filelist, "exclude_fids": []}
        headers = self.common_headers()
        response = await fetch(session, "POST", url, json=payload, headers=headers, params=querystring)
        return response

    async def recycle_list(self, session: aiohttp.ClientSession, page: int = 1, size: int = 30) -> List[Dict[str, Any]]:
        url = "https://drive-pc.quark.cn/1/clouddrive/file/recycle/list"
        querystring = {
            "_page": page,
            "_size": size,
            "pr": "ucpro",
            "fr": "pc",
            "uc_param_str": "",
        }
        headers = self.common_headers()
        response = await fetch(session, "GET", url, headers=headers, params=querystring)
        if response:
            return response["data"]["list"]
        else:
            return []

    async def recycle_remove(self, session: aiohttp.ClientSession, record_list: List[str]) -> Optional[Dict[str, Any]]:
        url = "https://drive-pc.quark.cn/1/clouddrive/file/recycle/remove"
        querystring = {"uc_param_str": "", "fr": "pc", "pr": "ucpro"}
        payload = {
            "select_mode": 2,
            "record_list": record_list,
        }
        headers = self.common_headers()
        response = await fetch(session, "POST", url, json=payload, headers=headers, params=querystring)
        return response

    async def update_savepath_fid(self, session: aiohttp.ClientSession, tasklist: List[Dict[str, Any]]) -> bool:
        dir_paths = [
            re.sub(r"/{2,}", "/", f"/{item['savepath']}")
            for item in tasklist
            if not item.get("enddate")
            or (
                datetime.now().date()
                <= datetime.strptime(item["enddate"], "%Y-%m-%d").date()
            )
        ]
        if not dir_paths:
            return False
        dir_paths_exist_arr = await self.get_fids(session, tuple(dir_paths))
        dir_paths_exist = [item["file_path"] for item in dir_paths_exist_arr]
        dir_paths_unexist = list(set(dir_paths) - set(dir_paths_exist) - set(["/"]))
        tasks = []
        for dir_path in dir_paths_unexist:
            tasks.append(self.mkdir(session, dir_path))
        mkdir_results = await asyncio.gather(*tasks)
        for dir_path, mkdir_return in zip(dir_paths_unexist, mkdir_results):
            if mkdir_return and mkdir_return.get("code") == 0:
                new_dir = mkdir_return["data"]
                dir_paths_exist_arr.append(
                    {"file_path": dir_path, "fid": new_dir["fid"]}
                )
                logger.info(f"创建文件夹：{dir_path}")
            else:
                logger.error(f"创建文件夹：{dir_path} 失败, {mkdir_return['message'] if mkdir_return else '无响应'}")
        # 储存目标目录的fid
        for dir_path in dir_paths_exist_arr:
            self.savepath_fid[dir_path["file_path"]] = dir_path["fid"]
        return True

    async def do_save_check(self, session: aiohttp.ClientSession, shareurl: str, savepath: str) -> Union[Dict[str, Any], bool]:
        try:
            result = self.get_id_from_url(shareurl)
            if result is None:
                return False
            pwd_id, pdir_fid = result
            is_sharing, stoken = await self.get_stoken(session, pwd_id)
            if not is_sharing:
                add_notify(f"❌：{stoken}\n")
                return False
            share_file_list = await self.get_detail(session, pwd_id, stoken, pdir_fid)
            fid_list = [item["fid"] for item in share_file_list]
            fid_token_list = [item["share_fid_token"] for item in share_file_list]
            file_name_list = [item["file_name"] for item in share_file_list]
            if not fid_list:
                return False
            
            get_fids = await self.get_fids(session, (savepath,))
            to_pdir_fid = None
            if get_fids and len(get_fids) > 0:
                to_pdir_fid = get_fids[0]["fid"]
            else:
                mkdir_result = await self.mkdir(session, savepath)
                if mkdir_result and mkdir_result.get("data"):
                    to_pdir_fid = mkdir_result["data"]["fid"]
                else:
                    logger.error(f"创建目录失败: {savepath}")
                    return False
            
            save_file_return = await self.save_file(session, fid_list, fid_token_list, to_pdir_fid, pwd_id, stoken)
            if not save_file_return:
                return False
            if save_file_return["code"] == 41017:
                return False
            elif save_file_return["code"] == 0:
                dir_file_list = await self.ls_dir(session, to_pdir_fid)
                del_list = [
                    item["fid"]
                    for item in dir_file_list
                    if (item["file_name"] in file_name_list)
                    and ((datetime.now().timestamp() - item["created_at"]) < 60)
                ]
                if del_list:
                    await self.delete(session, del_list)
                    recycle_list = await self.recycle_list(session)
                    record_id_list = [
                        item["record_id"]
                        for item in recycle_list
                        if item["fid"] in del_list
                    ]
                    await self.recycle_remove(session, record_id_list)
                return save_file_return
            else:
                return False
        except Exception as e:
            if os.environ.get("DEBUG") == "True":
                logger.error(f"转存测试失败: {str(e)}")
            return False

    async def do_save_task(self, session: aiohttp.ClientSession, task: Dict[str, Any]) -> Optional[bool]:
        if task.get("shareurl_ban"):
            logger.info(f"《{task['taskname']}》：{task['shareurl_ban']}")
            return None

        result = self.get_id_from_url(task["shareurl"])
        if result is None:
            return None
        pwd_id, pdir_fid = result
        is_sharing, stoken = await self.get_stoken(session, pwd_id)
        if not is_sharing:
            add_notify(f"❌《{task['taskname']}》：{stoken}\n")
            task["shareurl_ban"] = stoken
            return
        updated_tree = await self.dir_check_and_save(session, task, pwd_id, stoken, pdir_fid)
        if updated_tree.size(1) > 0:
            add_notify(f"✅《{task['taskname']}》添加追更：\n{updated_tree}")
            return True
        else:
            logger.info(f"任务结束：没有新的转存任务")
            return False

    async def dir_check_and_save(self, session: aiohttp.ClientSession, task: Dict[str, Any], pwd_id: str, stoken: str, pdir_fid: str = "", subdir_path: str = "") -> Tree:
        tree = Tree()
        tree.create_node(task["savepath"], pdir_fid)
        share_file_list = await self.get_detail(session, pwd_id, stoken, pdir_fid)

        if not share_file_list:
            if subdir_path == "":
                task["shareurl_ban"] = "分享为空，文件已被分享者删除"
                add_notify(f"《{task['taskname']}》：{task['shareurl_ban']}")
            return tree
        elif (
            len(share_file_list) == 1
            and share_file_list[0]["dir"]
            and subdir_path == ""
        ):
            logger.info("🧠 该分享是一个文件夹，读取文件夹内列表")
            share_file_list = await self.get_detail(session, pwd_id, stoken, share_file_list[0]["fid"])

        savepath = re.sub(r"/{2,}", "/", f"/{task['savepath']}{subdir_path}")
        if not self.savepath_fid.get(savepath):
            get_fids = await self.get_fids(session, (savepath,))
            if get_fids:
                self.savepath_fid[savepath] = get_fids[0]["fid"]
            else:
                # 尝试创建目录，就像do_save_check方法中那样
                logger.info(f"目录 {savepath} 不存在，尝试创建...")
                mkdir_result = await self.mkdir(session, savepath)
                if mkdir_result and mkdir_result.get("code") == 0:
                    self.savepath_fid[savepath] = mkdir_result["data"]["fid"]
                    logger.info(f"✅ 成功创建目录 {savepath}，fid: {mkdir_result['data']['fid']}")
                else:
                    logger.error(f"❌ 目录 {savepath} 创建失败，跳过转存")
                    return tree
        to_pdir_fid = self.savepath_fid[savepath]
        dir_file_list = await self.ls_dir(session, to_pdir_fid)

        need_save_list = []
        for share_file in share_file_list:
            if share_file["dir"] and task.get("update_subdir", False):
                pattern, replace = task["update_subdir"], ""
            else:
                # 如果没有pattern和replace字段，则匹配所有文件
                if 'pattern' not in task:
                    pattern, replace = ".*", ""
                else:
                    pattern, replace = magic_regex_func(task["pattern"], task["replace"])
            if re.search(pattern, share_file["file_name"]):
                save_name = (
                    re.sub(pattern, replace, share_file["file_name"])
                    if replace != ""
                    else share_file["file_name"]
                )
            if task.get("ignore_extension") and not share_file["dir"]:
                def compare_func(a: str, b1: str, b2: str) -> bool:
                    return (os.path.splitext(a)[0] == os.path.splitext(b1)[0]
                            or os.path.splitext(a)[0] == os.path.splitext(b2)[0])
            else:
                def compare_func(a: str, b1: str, b2: str) -> bool:
                    return a == b1 or a == b2
                file_exists = any(
                    compare_func(
                        dir_file["file_name"], share_file["file_name"], save_name
                    )
                    for dir_file in dir_file_list
                )
                if not file_exists:
                    share_file["save_name"] = save_name
                    need_save_list.append(share_file)
                elif share_file["dir"]:
                    if task.get("update_subdir", False):
                        logger.info(f"检查子文件夹：{savepath}/{share_file['file_name']}")
                        subdir_tree = await self.dir_check_and_save(
                            session,
                            task,
                            pwd_id,
                            stoken,
                            share_file["fid"],
                            f"{subdir_path}/{share_file['file_name']}",
                        )
                        if subdir_tree.size(1) > 0:
                            tree.create_node(
                                "📁" + share_file["file_name"],
                                share_file["fid"],
                                parent=pdir_fid,
                            )
                            tree.merge(share_file["fid"], subdir_tree, deep=False)
            if share_file["fid"] == task.get("startfid", ""):
                break

        fid_list = [item["fid"] for item in need_save_list]
        fid_token_list = [item["share_fid_token"] for item in need_save_list]
        save_name_list = [item["save_name"] for item in need_save_list]
        if fid_list:
            save_file_return = await self.save_file(session, fid_list, fid_token_list, to_pdir_fid, pwd_id, stoken)
            err_msg = None
            if save_file_return and save_file_return.get("code") == 0:
                task_id = save_file_return["data"]["task_id"]
                query_task_return = await self.query_task(session, task_id)
                if query_task_return and query_task_return.get("code") == 0:
                    save_name_list.sort()
                    for item in need_save_list:
                        icon = (
                            "📁"
                            if item["dir"]
                            else "🎞️" if item["obj_category"] == "video" else ""
                        )
                        tree.create_node(
                            f"{icon}{item['save_name']}", item["fid"], parent=pdir_fid
                        )
                else:
                    err_msg = query_task_return["message"] if query_task_return else "无响应"
            else:
                err_msg = save_file_return["message"] if save_file_return else "无响应"

            if err_msg:
                add_notify(f"❌《{task['taskname']}》转存失败：{err_msg}\n")
        return tree

    async def query_task(self, session: aiohttp.ClientSession, task_id: str) -> Optional[Dict[str, Any]]:
        retry_index = 0
        while True:
            url = "https://drive-pc.quark.cn/1/clouddrive/task"
            querystring = {
                "pr": "ucpro",
                "fr": "pc",
                "uc_param_str": "",
                "task_id": task_id,
                "retry_index": retry_index,
                "__dt": int(random.uniform(1, 5) * 60 * 1000),
                "__t": datetime.now().timestamp(),
            }
            headers = self.common_headers()
            response = await fetch(session, "GET", url, headers=headers, params=querystring)
            if response:
                if response["data"]["status"] != 0:
                    break
                else:
                    if retry_index == 0:
                        logger.info(f"正在等待[{response['data']['task_title']}]执行结果")
                    else:
                        logger.info(".")
                    retry_index += 1
                    await asyncio.sleep(0.5)
            else:
                break
        return response

    async def do_rename_task(self, session: aiohttp.ClientSession, task: Dict[str, Any], subdir_path: str = "") -> bool:
        # 检查任务是否有pattern和replace字段
        if "pattern" not in task or "replace" not in task:
            # 如果没有pattern和replace字段，跳过重命名任务
            return False
        pattern, replace = magic_regex_func(task["pattern"], task["replace"])
        if not pattern or not replace:
            return False
        savepath = re.sub(r"/{2,}", "/", f"/{task['savepath']}{subdir_path}")
        if not self.savepath_fid.get(savepath):
            fids = await self.get_fids(session, (savepath,))
            if fids:
                self.savepath_fid[savepath] = fids[0]["fid"]
            else:
                return False
        dir_file_list = await self.ls_dir(session, self.savepath_fid[savepath])
        dir_file_name_list = [item["file_name"] for item in dir_file_list]
        rename_tasks = []
        for dir_file in dir_file_list:
            if dir_file["dir"]:
                rename_tasks.append(self.do_rename_task(session, task, f"{subdir_path}/{dir_file['file_name']}"))
            if re.search(pattern, dir_file["file_name"]):
                save_name = (
                    re.sub(pattern, replace, dir_file["file_name"])
                    if replace != ""
                    else dir_file["file_name"]
                )
                if save_name != dir_file["file_name"] and (
                    save_name not in dir_file_name_list
                ):
                    rename_tasks.append(self.rename(session, dir_file["fid"], save_name))
        rename_results = await asyncio.gather(*rename_tasks)
        is_rename = any(rename_results)
        return is_rename

async def verify_account(session: aiohttp.ClientSession, account: Quark) -> bool:
    logger.info(f"▶️ 验证第{account.index}个账号")
    if "__uid" not in account.cookie:
        logger.info(f"💡 不存在cookie必要参数，判断为仅签到")
        return False
    else:
        account_info = await account.init(session)
        if not account_info:
            add_notify(f"👤 第{account.index}个账号登录失败，cookie无效❌")
            return False
        else:
            logger.info(f"👤 账号昵称: {account_info['nickname']}✅")
            return True

def format_bytes(size_bytes: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = 0
    size_float = float(size_bytes)
    while size_float >= 1024 and i < len(units) - 1:
        size_float /= 1024
        i += 1
    return f"{size_float:.2f} {units[i]}"

async def do_sign(session: aiohttp.ClientSession, account: Quark) -> None:
    if not account.mparam:
        logger.info("⏭️ 移动端参数未设置，跳过签到")
        return
    growth_info = await account.get_growth_info(session)
    if growth_info and isinstance(growth_info, dict):
        # 安全地访问字典键
        is_88vip = growth_info.get('88VIP', False)
        total_capacity = growth_info.get('total_capacity', 0)
        cap_composition = growth_info.get('cap_composition', {})
        sign_reward = cap_composition.get('sign_reward', 0)
        
        growth_message = f"💾 {'88VIP' if is_88vip else '普通用户'} 总空间：{format_bytes(total_capacity)}，签到累计获得：{format_bytes(sign_reward)}"
        
        cap_sign = growth_info.get('cap_sign', {})
        if isinstance(cap_sign, dict) and cap_sign.get('sign_daily'):
            sign_daily_reward = cap_sign.get('sign_daily_reward', 0)
            sign_progress = int(cap_sign.get('sign_progress', 0))
            sign_target = int(cap_sign.get('sign_target', 0))
            
            # 安全地进行除法运算
            reward_mb = 0
            if sign_daily_reward:
                try:
                    reward_mb = int(sign_daily_reward / 1024 / 1024)
                except (TypeError, ValueError):
                    reward_mb = 0
            sign_message = f"📅 签到记录: 今日已签到+{reward_mb}MB，连签进度({sign_progress}/{sign_target})✅"
            message = f"{sign_message}\n{growth_message}"
            logger.info(message)
        else:
            sign, sign_return = await account.get_growth_sign(session)
            if sign:
                sign_progress = int(cap_sign.get('sign_progress', 0))
                sign_target = int(cap_sign.get('sign_target', 0))
                
                # 安全地进行除法运算
                sign_return_mb = 0
                if isinstance(sign_return, (int, float)):
                    try:
                        sign_return_mb = int(sign_return / 1024 / 1024)
                    except (TypeError, ValueError):
                        sign_return_mb = 0
                sign_message = f"📅 执行签到: 今日签到+{sign_return_mb}MB，连签进度({sign_progress + 1}/{sign_target})✅"
                message = f"{sign_message}\n{growth_message}"
                
                # 移除签到通知功能，只记录日志
                logger.info(message)
            else:
                logger.error(f"📅 签到异常: {sign_return}")

async def do_save(session: aiohttp.ClientSession, account: Quark, tasklist: List[Dict[str, Any]] = []) -> None:
    emby = Emby(
        CONFIG_DATA.get("emby", {}).get("url", ""),
        CONFIG_DATA.get("emby", {}).get("apikey", ""),
    )
    logger.info(f"转存账号: {account.nickname}")
    await account.update_savepath_fid(session, tasklist)

    def check_date(task):
        return (
            (not task.get("enddate") or datetime.now().date() <= datetime.strptime(task["enddate"], "%Y-%m-%d").date())
            and (
                not task.get("runweek")
                or (datetime.today().weekday() + 1 in task.get("runweek"))
            )
        )

    tasks = []
    for index, task in enumerate(tasklist):
        if check_date(task):
            logger.info(f"#{index+1}------------------")
            logger.info(f"任务名称: {task['taskname']}")
            logger.info(f"分享链接: {task['shareurl']}")
            logger.info(f"目标目录: {task['savepath']}")
            if 'pattern' in task:
                logger.info(f"正则匹配: {task['pattern']}")
            if 'replace' in task:
                logger.info(f"正则替换: {task['replace']}")
            if task.get("enddate"):
                logger.info(f"任务截止: {task['enddate']}")
            if task.get("emby_id"):
                logger.info(f"刷媒体库: {task['emby_id']}")
            if task.get("ignore_extension"):
                logger.info(f"忽略后缀: {task['ignore_extension']}")
            if task.get("update_subdir"):
                logger.info(f"更子目录: {task['update_subdir']}")
            is_new = await account.do_save_task(session, task)
            is_rename = await account.do_rename_task(session, task)
            if emby.is_active and (is_new or is_rename) and task.get("emby_id") != "0":
                if task.get("emby_id"):
                    await emby.refresh(session, task["emby_id"])
                else:
                    match_emby_id = await emby.search(session, task["taskname"])
                    if match_emby_id:
                        task["emby_id"] = match_emby_id
                        await emby.refresh(session, match_emby_id)
    logger.info("转存任务完成")

class Emby:
    def __init__(self, emby_url: str, emby_apikey: str):
        self.is_active = False
        if emby_url and emby_apikey:
            self.emby_url = emby_url
            self.emby_apikey = emby_apikey
            # 初始化时不进行请求，需要在异步环境中调用方法

    async def get_info(self, session):
        url = f"{self.emby_url}/emby/System/Info"
        headers = {"X-Emby-Token": self.emby_apikey}
        response = await fetch(session, "GET", url, headers=headers, params={})
        if response and "application/json" in response.get("Content-Type", ""):
            logger.info(
                f"Emby媒体库: {response.get('ServerName','')} v{response.get('Version','')}"
            )
            return True
        else:
            logger.error(f"Emby媒体库: 连接失败❌ {response.get('text', '无响应') if response else '无响应'}")
            return False

    async def refresh(self, session, emby_id):
        if emby_id:
            url = f"{self.emby_url}/emby/Items/{emby_id}/Refresh"
            headers = {"X-Emby-Token": self.emby_apikey}
            querystring = {
                "Recursive": "true",
                "MetadataRefreshMode": "FullRefresh",
                "ImageRefreshMode": "FullRefresh",
                "ReplaceAllMetadata": "false",
                "ReplaceAllImages": "false",
            }
            response = await fetch(session, "POST", url, headers=headers, params=querystring)
            if response and response.get("text") == "":
                logger.info(f"🎞 刷新Emby媒体库：成功✅")
                return True
            else:
                logger.error(f"🎞 刷新Emby媒体库：{response.get('text', '无响应') if response else '无响应'}❌")
                return False

    async def search(self, session, media_name):
        if media_name:
            url = f"{self.emby_url}/emby/Items"
            headers = {"X-Emby-Token": self.emby_apikey}
            querystring = {
                "IncludeItemTypes": "Series",
                "StartIndex": 0,
                "SortBy": "SortName",
                "SortOrder": "Ascending",
                "ImageTypeLimit": 0,
                "Recursive": "true",
                "SearchTerm": media_name,
                "Limit": 10,
                "IncludeSearchTypes": "false",
            }
            response = await fetch(session, "GET", url, headers=headers, params=querystring)
            if response and "application/json" in response.get("Content-Type", ""):
                if response.get("Items"):
                    for item in response["Items"]:
                        if item["IsFolder"]:
                            logger.info(
                                f"🎞 《{item['Name']}》匹配到Emby媒体库ID：{item['Id']}"
                            )
                            return item["Id"]
            else:
                logger.error(f"🎞 搜索Emby媒体库：{response.get('text', '无响应') if response else '无响应'}❌")
        return False

async def main():
    global CONFIG_DATA
    start_time = datetime.now()
    logger.info("===============程序开始===============")
    logger.info(f"⏰ 执行时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    config_path = sys.argv[1] if len(sys.argv) > 1 else "quark_config.json"
    
    # 解析命令行参数
    task_index = None
    cookie_index = None
    
    if len(sys.argv) > 2:
        # 检查第二个参数是否是数字（可能是task_index或cookie_index）
        if sys.argv[2].isdigit():
            # 当Web界面调用时，第二个参数是cookie_index
            # 当命令行调用时，可能是task_index
            # 为了兼容性，我们假设当只有两个参数时，第二个是cookie_index
            # 当有三个参数时，第二个是task_index，第三个是cookie_index
            if len(sys.argv) == 3:
                # 只有两个参数：config.json cookie_index
                cookie_index = int(sys.argv[2])
            elif len(sys.argv) > 3:
                # 有三个或更多参数：config.json task_index cookie_index
                task_index = int(sys.argv[2])
                if sys.argv[3].isdigit():
                    cookie_index = int(sys.argv[3])

    if not os.path.exists(config_path):
        if os.environ.get("QUARK_COOKIE"):
            logger.info(
                f"⚙️ 读取到 QUARK_COOKIE 环境变量，仅签到领空间。如需执行转存，请删除该环境变量后配置 {config_path} 文件"
            )
            cookie_val = os.environ.get("QUARK_COOKIE")
            cookie_form_file = False
        else:
            logger.info(f"⚙️ 配置文件 {config_path} 不存在❌，正远程从下载配置模版")
            config_url = f"{GH_PROXY}https://raw.githubusercontent.com/Cp0204/quark_auto_save/main/quark_config.json"
            if download_file_sync(config_url, config_path):
                logger.info("⚙️ 配置模版下载成功✅，请到程序目录中手动配置")
            return
    else:
        logger.info(f"⚙️ 正从 {config_path} 文件中读取配置")
        with open(config_path, "r", encoding="utf-8") as file:
            CONFIG_DATA = json.load(file)
        if not CONFIG_DATA.get("magic_regex"):
            CONFIG_DATA["magic_regex"] = MAGIC_REGEX
        cookie_form_file = True

    # 支持新的cookies数组结构
    if "cookies" in CONFIG_DATA:
        # 新结构：cookies数组，每个cookie有自己的tasklist
        cookies_data = CONFIG_DATA["cookies"]
        cookies = [cookie_data["cookie"] for cookie_data in cookies_data]
        cookie_names = [cookie_data["name"] for cookie_data in cookies_data]
        cookie_tasklists = [cookie_data.get("tasklist", []) for cookie_data in cookies_data]
    else:
        # 旧结构：兼容处理
        cookie_val = CONFIG_DATA.get("cookie")
        cookies_result = get_cookies(cookie_val)
        if isinstance(cookies_result, list):
            cookies = cookies_result
            cookie_names = [f"账号{i+1}" for i in range(len(cookies))]
            cookie_tasklists = [CONFIG_DATA.get("tasklist", [])] * len(cookies)
        else:
            cookies = []
            cookie_names = []
            cookie_tasklists = []

    if not cookies:
        logger.error("❌ cookie 未配置")
        return

    async with aiohttp.ClientSession() as session:
        accounts = [Quark(cookie, index) for index, cookie in enumerate(cookies)]
        logger.info("===============验证账号===============")
        verify_tasks = [verify_account(session, account) for account in accounts]
        await asyncio.gather(*verify_tasks)
        logger.info("===============签到任务===============")
        sign_tasks = [do_sign(session, account) for account in accounts]
        await asyncio.gather(*sign_tasks)
        logger.info("===============转存任务===============")
        
        # 为每个有效的账号执行对应的转存任务
        for i, account in enumerate(accounts):
            if account.is_active and cookie_form_file and i < len(cookie_tasklists):
                tasklist = cookie_tasklists[i]
                if tasklist:  # 只有该cookie有任务时才执行转存
                    # 如果指定了cookie_index，只处理该cookie
                    if cookie_index is not None and i != cookie_index:
                        continue
                    
                    logger.info(f"===============处理账号: {cookie_names[i]} ===============")
                    if task_index is not None and 0 <= task_index < len(tasklist):
                        await do_save(session, account, [tasklist[task_index]])
                    else:
                        await do_save(session, account, tasklist)
                    
                    # 处理完当前账号后，发送该账号的通知
                    if NOTIFYS:
                        notify_body = "\n".join(NOTIFYS)
                        send_ql_notify("【夸克自动追更】", notify_body, cookie_index=i)
                        # 清空NOTIFYS，为下一个账号做准备
                        NOTIFYS.clear()
        
        logger.info("===============推送通知===============")
        # 这里不再需要发送通知，因为每个账号处理完后已经发送了
        if cookie_form_file:
            with open(config_path, "w", encoding="utf-8") as file:
                json.dump(CONFIG_DATA, file, ensure_ascii=False, indent=2)
    end_time = datetime.now()
    duration = end_time - start_time
    logger.info("===============程序结束===============")
    logger.info(f"😃 运行时长: {round(duration.total_seconds(), 2)}s")

if __name__ == "__main__":
    asyncio.run(main())
