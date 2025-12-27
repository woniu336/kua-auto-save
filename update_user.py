import re

# 设置文件路径
app_file = '/root/kua-auto-save/app.py'

# 提示输入用户名和密码
username = input("请输入用户名: ")
password = input("请输入密码: ")

# 检查用户名和密码是否为空
if not username or not password:
    print("用户名和密码不能为空！")
    exit(1)

# 读取文件内容
with open(app_file, 'r') as file:
    file_content = file.read()

# 查找 VALID_USERS 字段并修改
valid_users_pattern = r'VALID_USERS = {.*?}'
match = re.search(valid_users_pattern, file_content, re.DOTALL)

if match:
    # 替换 VALID_USERS 中的内容
    valid_users_block = match.group(0)
    new_valid_users = f'VALID_USERS = {{\n    "{username}": "{password}",\n}}'

    # 替换文件中的 VALID_USERS 字段
    updated_content = file_content.replace(valid_users_block, new_valid_users)

    # 写回文件
    with open(app_file, 'w') as file:
        file.write(updated_content)

    print("用户名和密码已成功更新！")
else:
    print("未找到 VALID_USERS 字段！")
