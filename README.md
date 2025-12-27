


## 一键部署脚本

```
curl -sS -O https://raw.githubusercontent.com/woniu336/kua-auto-save/main/save_kua.sh && chmod +x save_kua.sh && ./save_kua.sh install
```


修改密码：

```
curl -sSL https://raw.githubusercontent.com/woniu336/kua-auto-save/main/update_user.py -o update_user.py && python3 update_user.py
```


定时删除备份文件

```
(crontab -l 2>/dev/null; echo "10 4 * * 1 find /root/kua-auto-save/backups/ -name '*.json' -type f -delete") | crontab -
```




## 定时任务


```
(crontab -l 2>/dev/null; echo "0 8,12,20 * * * cd $HOME/kua-auto-save && /usr/bin/python3 quark_auto_save.py") | crontab -
```

查看日志
```
tail -n 20 /root/kua-auto-save/quark_save.log
```

## 清理日志

```
(crontab -l 2>/dev/null; echo "0 3 * * * cd $HOME/kua-auto-save && /usr/bin/python3 clean_log_simple.py 2>&1 | logger -t save_kua") | crontab -
```

验证是否添加成功

```
crontab -l
```



## 卸载

```
./save_kua.sh stop
rm -rf ~/kua-auto-save
```

