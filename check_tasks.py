import json

with open('quark_config.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print("=== 当前账号任务统计 ===")
for i, account in enumerate(data['cookies']):
    account_name = account['name']
    task_count = len(account['tasklist'])
    print(f"账号 {i}: {account_name} - {task_count} 个任务")
    
    if task_count > 0:
        print(f"  任务列表:")
        for j, task in enumerate(account['tasklist']):
            print(f"    {j}: {task['taskname']} - {task['shareurl'][:30]}...")
    print()
