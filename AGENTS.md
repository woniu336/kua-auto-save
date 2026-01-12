# AGENTS.md

This file contains instructions for agentic coding agents working in this repository.

## Project Overview

This is a Python Flask web application for managing Quark cloud storage automation tasks. It provides a web interface for configuring accounts, managing save tasks, and scheduling automated file transfers from Quark cloud shares.

## Build/Lint/Test Commands

### Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Run main Flask web application (port 5000)
python app.py

# Run simple admin interface
python simple_admin/app.py

# Run alternative Flask app (port 5005)
python app/run.py

# Execute Quark auto-save script
python quark_auto_save.py quark_config.json
```

### Testing

**Note**: This project does not have a formal test suite. Manual testing is performed by:

```bash
# Run the automation script to test core functionality
python quark_auto_save.py quark_config.json

# Test with specific account index
python quark_auto_save.py quark_config.json <account_index>

# Check log output for validation
tail -f quark_save.log
```

### No Linting/Type Checking

This project does not currently use any automated linting or type checking tools. Ensure code follows the conventions outlined below.

## Code Style Guidelines

### Imports and Module Structure

- Standard library imports first, followed by third-party imports, then local imports
- Group imports logically with blank lines between groups
- Use `from typing import Dict, List, Any, Optional, Tuple, Union` for type hints
- Example:

```python
import os
import json
import asyncio
from datetime import datetime

import aiohttp
from flask import Flask, render_template
```

### File Encoding

All Python files MUST include UTF-8 encoding declaration:
```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
```

### Naming Conventions

- **Variables and functions**: `snake_case`
  ```python
  def save_file():
      account_index = 0
      invalid_links = []
  ```

- **Classes**: `PascalCase`
  ```python
  class QuarkManager:
      class Emby:
  ```

- **Constants**: `UPPER_SNAKE_CASE`
  ```python
  CONFIG_FILE = 'quark_config.json'
  BACKUP_DIR = 'backups'
  ```

- **Private methods/attributes**: prefix with underscore
  ```python
  def _clean(self, value):
      self._fids_cache = {}
  ```

### Type Hints

- Use type hints for function signatures and variables where feasible
- Import from `typing` module: `Dict, List, Any, Optional, Tuple, Union`
- Example:
  ```python
  def get_account(self, account_index: int) -> Optional[Dict[str, Any]]:
      config = self.load_config()
      if 0 <= account_index < len(config["cookies"]):
          return config["cookies"][account_index]
      return None
  ```

### Async/Await Pattern

- This codebase extensively uses async/await with `aiohttp`
- Always use `async with aiohttp.ClientSession()` for HTTP requests
- Example:
  ```python
  async def get_account_info(self, session: aiohttp.ClientSession) -> Union[Dict[str, Any], bool]:
      url = "https://pan.quark.cn/account/info"
      response = await fetch(session, "GET", url, headers=self.common_headers())
      return response["data"] if response else False
  ```

### Error Handling

- Use try/except blocks for operations that may fail
- Log errors using `logger.error()` with descriptive messages
- Return meaningful error messages to callers
- Example:
  ```python
  try:
      with open(config_file, 'r', encoding='utf-8') as f:
          return json.load(f)
  except json.JSONDecodeError as e:
      logger.error(f"配置文件JSON格式错误: {e}")
      return {"cookies": []}
  except Exception as e:
      logger.error(f"加载配置文件失败: {e}")
      return {"cookies": []}
  ```

### Logging

- Configure logger at module level
- Use appropriate log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`
- Include context in log messages
- Example:
  ```python
  logger = logging.getLogger(__name__)
  logger.info(f"处理账号: {account_name}")
  logger.error(f"保存配置文件失败: {e}")
  ```

### Flask Application Structure

- Define routes with decorators
- Use `@login_required` decorator for protected routes
- Use `flash()` for user feedback messages
- Return `jsonify()` for API endpoints
- Example:
  ```python
  @app.route('/account/<int:account_id>')
  @login_required
  def account_detail(account_id):
      account = manager.get_account(account_id)
      if account:
          return jsonify(account)
      return jsonify({'error': '账号不存在'}), 404
  ```

### Configuration Management

- Configuration stored in JSON files (e.g., `quark_config.json`)
- Use `ensure_ascii=False, indent=2` for JSON dumps
- Always use UTF-8 encoding for file operations
- Create backups before modifying config files

### Session Management

- Flask sessions expire after 48 hours by default
- Store login state in session: `session['logged_in'] = True`
- Use `@login_required` decorator for authentication

### Chinese Language

- This codebase uses Chinese for user-facing strings, comments, and documentation
- Use UTF-8 encoding for all files containing Chinese characters
- Log messages in Chinese for better user experience

### HTML Templates

- Templates use Jinja2 syntax
- Use Bootstrap CSS framework
- Variable placeholders: `{{ variable }}`
- Static files in `static/` directory

### File Paths

- Use `os.path.join()` for cross-platform path handling
- Use absolute paths where appropriate
- Example:
  ```python
  CONFIG_FILE = os.path.join(PARENT_DIR, "quark_config.json")
  ```

## File Organization

```
kua-auto-save/
├── app.py                      # Main Flask web application
├── quark_auto_save.py          # Core automation logic
├── simple_admin/               # Admin interface
│   ├── app.py
│   └── templates/
├── app/                        # Alternative Flask app
│   ├── run.py
│   └── templates/
├── templates/                  # HTML templates for main app
├── static/                     # CSS, JS, favicon
├── requirements.txt            # Python dependencies
├── quark_config.json           # Main configuration file
├── save_kua.sh                 # Deployment script
└── quark_save.log              # Application log file
```

## Important Notes

- No automated tests - test changes manually before committing
- No linting - review code carefully for style consistency
- Configuration files use UTF-8 encoding with Chinese characters
- Multiple Flask applications serve different purposes
- Async operations use `aiohttp` exclusively
- All file I/O operations should use UTF-8 encoding
