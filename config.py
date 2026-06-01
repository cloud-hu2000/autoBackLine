import os

from dotenv import load_dotenv

load_dotenv()

"""
配置文件
请根据实际目标网站修改以下配置
"""

# ============== 网站配置 ==============
SITE_CONFIG = {
    "url": "https://dash.3ue.co/",  # 目标网站URL
    "login_url": "https://dash.3ue.co/zh-Hans/#/login",  # 登录页面URL
    "home_url": "https://dash.3ue.co/zh-Hans/#/page/m/home",  # 首页URL
    "timeout": 30000,  # 页面加载超时时间(毫秒)
}

# ============== 登录凭据 ==============
# 建议使用环境变量或从安全存储中读取
LOGIN_CREDENTIALS = {
    "username": os.getenv("LOGIN_USERNAME", ""),
    "password": os.getenv("LOGIN_PASSWORD", ""),
}

# ============== 登录表单选择器 ==============
# 需要根据实际网站修改
LOGIN_SELECTORS = {
    "username_input": 'input[name="username"], #input-username',
    "password_input": 'input[name="password"], #input-password',
    "submit_button": 'button[nbbutton], button[type="submit"], button.appearance-filled',
    "logged_in_indicator": '.user-info, .username, [data-testid="user-menu"]',  # 登录成功标识
}

# ============== 数据抓取配置 ==============
SCRAPE_CONFIG = {
    "data_url": "https://sem.3ue.co/analytics/backlinks/overview",  # 数据页面URL
    "domain_source": "excel",  # 域名来源: "excel"=从Excel读取, "config"=使用下面配置的固定域名
    "default_domain": "heartratetap.com",  # 固定域名（domain_source为config时使用）
    "table_selector": "table.data-table, .table, #data-table",  # 数据表格选择器
    "rows_selector": "tbody tr, .data-row",  # 数据行选择器
    "columns": [  # 列配置
        {"name": "序号", "selector": "td:nth-child(1)"},
        {"name": "名称", "selector": "td:nth-child(2)"},
        {"name": "类型", "selector": "td:nth-child(3)"},
        {"name": "状态", "selector": "td:nth-child(4)"},
        {"name": "时间", "selector": "td:nth-child(5)"},
    ],
    "pagination": {
        "enabled": True,
        "next_button": ".pagination .next, .page-next",
        "max_pages": 10,  # 最大翻页数
    },
}

# ============== 搜索配置 ==============
SEARCH_CONFIG = {
    "search_url": "https://www.example.com/search",
    "search_input": 'input[name="keyword"], #search-input, .search-box input',
    "search_button": 'button.search-btn, .search-button, button[type="submit"]',
    "result_selector": ".search-result, .result-item, .data-list",
    "result_item_selectors": {  # 搜索结果字段映射
        "title": ".title, h3",
        "content": ".content, .description",
        "link": "a",
    },
}

# ============== Excel配置 ==============
EXCEL_CONFIG = {
    "input_file": "data/input.xlsx",  # 输入文件（搜索关键词和域名）
    "output_file": "data/output.xlsx",  # 输出文件
    "input_sheet": "Sheet1",  # 输入文件工作表名
    "output_sheet": "数据",  # 输出文件工作表名
    "input_keyword_column": "关键词",  # 输入文件中关键词列名
    "input_domain_column": "域名",  # 输入文件中域名列名（Semrush用）
    "output_columns": [  # 输出文件列配置
        "序号",
        "关键词",
        "搜索结果标题",
        "结果内容",
        "链接",
        "抓取时间",
    ],
    "semrush_output_columns": [  # Semrush反向链接输出列
        "序号",
        "域名",
        "来源URL",
        "来源Tag",
        "目标URL",
        "目标Tag",
        "反向链接数",
        "引用域名数",
        "抓取时间",
    ],
}

# ============== 浏览器配置 ==============
BROWSER_CONFIG = {
    "headless": False,  # 是否无头模式（调试时设为False）
    "slow_mo": 0,  # 操作延迟（毫秒），用于调试，0为不延迟
    "user_data_dir": "browser/data",  # 浏览器数据目录（保存cookie等）
    "screenshot_dir": "logs/screenshots",  # 截图保存目录
    "viewport": {"width": 1920, "height": 1080},
    "disable_images": True,  # 禁用图片加载，提升速度
    "use_existing_chrome": True,  # 是否使用已有的Chrome浏览器
    "chrome_path": r"C:\Program Files\Google\Chrome\Application\chrome.exe",  # Chrome浏览器路径，留空则自动查找
    "chrome_remote_debugging_port": 9222,  # 远程调试端口（使用已有Chrome时需要）
}

# ============== 节点选择配置 ==============
NODE_CONFIG = {
    "default_node": "节点17",  # 默认选择的节点
    "home_url": "https://dash.3ue.co/zh-Hans/#/page/m/home",  # 首页URL
}

NODE_SELECTORS = {
    # 节点下拉框 - nebular组件
    "node_dropdown": "nb-select button..+-button",
    # 节点选项容器
    "node_options_container": "nb-select-option",
    # 打开按钮
    "open_button": "button:has-text('打开')",
}

# ============== Semrush反向链接配置 ==============
SEMRUSH_CONFIG = {
    "base_url": "https://sem.3ue.co/analytics/backlinks/overview/",
    "overview_url": "https://sem.3ue.co/analytics/backlinks/overview/",
    "backlinks_url": "https://sem.3ue.co/analytics/backlinks/backlinks/",
    # 查询参数
    "params": {
        "q": "heartratetap.com",  # 查询的域名，从Excel读取
        "searchType": "domain",  # 搜索类型
        "__gmitm": os.getenv("SEMRUSH_GMITM", ""),  # 追踪参数，需要保存
    },
    # 输出CSV配置
    "output_csv": "data/backlinks_{domain}_{date}.csv",
    "output_columns": [
        "序号",
        "域名",
        "来源URL",
        "来源Tag",
        "目标URL",
        "目标Tag",
        "反向链接数",
        "引用域名数",
        "抓取时间",
    ],
}

# ============== Semrush 域名分析配置（输入域名 + 点击分析）==============
SEMRUSH_ANALYSIS_CONFIG = {
    "domain_input": '[data-ui-name="Input.Value"][placeholder="输入域名或 URL"]',
    "analyze_button": '[data-ui-name="Button.Text"]:has-text("分析")',
}

# ============== 升级弹窗配置 ==============
UPGRADE_POPUP_SELECTOR = '[data-ui-name="Button.Text"]:has-text("升级到 Guru")'

# ============== 反爬配置 ==============
ANTI_BAN_CONFIG = {
    "random_delay_min": 1,  # 最小随机延迟（秒）
    "random_delay_max": 3,  # 最大随机延迟（秒）
    "max_retries": 3,  # 最大重试次数
    "retry_delay": 5,  # 重试间隔（秒）
}

# ============== 日志配置 ==============
LOG_CONFIG = {
    "level": "INFO",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": "logs/app.log",
    "max_bytes": 10 * 1024 * 1024,  # 10MB
    "backup_count": 5,
}
