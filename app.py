from flask import Flask, render_template, request, jsonify, session
import requests
import logging

# --- 1. 配置日志记录 ---
# 设置日志记录器
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# --- 2. 初始化 Flask 应用 ---
app = Flask(__name__)
# 请务必修改为一个复杂且随机的字符串，以确保 session 安全
app.secret_key = 'your-super-secret-and-random-string-must-be-changed'

# --- 3. 企业微信 API 封装 (已加入日志) ---

def get_access_token(corpid, corpsecret, token_type="应用"):
    """通用获取 access_token 的函数"""
    url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corpid}&corpsecret={corpsecret}"
    logging.info(f"正在获取 [{token_type}Token]...")
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data.get("errcode") == 0:
            logging.info(f"成功获取 [{token_type}Token]！")
            return data.get("access_token"), None
        else:
            # 记录详细的错误日志
            error_msg = data.get('errmsg', '未知错误')
            error_code = data.get('errcode', 'N/A')
            logging.error(f"获取 [{token_type}Token] 失败！错误码: {error_code}, 错误信息: {error_msg}")
            return None, f"错误码: {error_code}, {error_msg}"
    except requests.RequestException as e:
        logging.error(f"获取 [{token_type}Token] 时网络请求失败: {e}")
        return None, str(e)

def get_departments_api(token):
    """获取全量组织架构"""
    url = f"https://qyapi.weixin.qq.com/cgi-bin/department/list?access_token={token}"
    logging.info("正在调用 API [获取部门列表]...")
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data.get("errcode") == 0:
            departments = data.get("department", [])
            logging.info(f"成功获取 {len(departments)} 个部门。")
            return departments, None
        else:
            error_msg = data.get('errmsg', '未知错误')
            error_code = data.get('errcode', 'N/A')
            logging.error(f"调用 API [获取部门列表] 失败！错误码: {error_code}, 错误信息: {error_msg}")
            return None, f"错误码: {error_code}, {error_msg}"
    except requests.RequestException as e:
        logging.error(f"调用 API [获取部门列表] 时网络请求失败: {e}")
        return None, str(e)

# ... 其他 API 函数保持原样，也可以按需添加日志 ...
# (为了简洁，这里省略其他API函数的日志，核心问题出在connect阶段)
def get_users_by_dept_api(token, department_id):
    """获取指定部门下的用户列表（不含子部门）"""
    url = f"https://qyapi.weixin.qq.com/cgi-bin/user/simplelist?access_token={token}&department_id={department_id}"
    logging.info(f"正在调用 API [获取部门成员], 部门ID: {department_id}...")
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()

        if data.get("errcode") == 0:
            users = data.get("userlist", [])
            logging.info(f"成功获取 {len(users)} 个成员。")
            return users, None  # 成功时，错误信息返回 None
        else:
            error_msg = data.get('errmsg', '未知错误')
            error_code = data.get('errcode', 'N/A')
            logging.error(f"调用 API [获取部门成员] 失败！错误码: {error_code}, 错误信息: {error_msg}")
            return None, f"错误码: {error_code}, {error_msg}" # 失败时，返回错误信息
            
    except requests.RequestException as e:
        logging.error(f"调用 API [获取部门成员] 时网络请求失败: {e}")
        return None, str(e)
        
def get_user_detail_api(token, userid):
    url = f"https://qyapi.weixin.qq.com/cgi-bin/user/get?access_token={token}&userid={userid}"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.json(), None
    except requests.RequestException as e:
        return None, str(e)

def create_user_api(token, user_data):
    url = f"https://qyapi.weixin.qq.com/cgi-bin/user/create?access_token={token}"
    response = requests.post(url, json=user_data)
    return response.json()

def update_user_api(token, user_data):
    url = f"https://qyapi.weixin.qq.com/cgi-bin/user/update?access_token={token}"
    response = requests.post(url, json=user_data)
    return response.json()
    
def delete_user_api(token, userid):
    url = f"https://qyapi.weixin.qq.com/cgi-bin/user/delete?access_token={token}&userid={userid}"
    response = requests.get(url)
    return response.json()

# --- 4. Flask 路由 (已加入日志) ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/connect', methods=['POST'])
def connect():
    """连接并获取初始数据"""
    logging.info("收到新的连接请求...")
    data = request.json
    session['corp_id'] = data.get('corp_id')
    session['app_secret'] = data.get('app_secret')
    session['txl_secret'] = data.get('txl_secret')

    token_read, error = get_access_token(session['corp_id'], session['app_secret'], token_type="应用")
    if not token_read:
        return jsonify({"success": False, "error": f"获取应用Token失败: {error}"})

    departments, error = get_departments_api(token_read)
    if error:
        return jsonify({"success": False, "error": f"获取组织架构失败: {error}"})
    
    # 初始加载根部门(id=1)的用户
    initial_users, error = get_users_by_dept_api(token_read, 1)
    
    # --- 核心修正点在这里 ---
    # 只有在明确返回了错误信息 (error is not None) 的情况下，才判定为失败
    if error is not None: 
        logging.error(f"获取根部门(id=1)用户列表失败: {error}")
        return jsonify({"success": False, "error": f"获取根部门用户失败: {error}"})
    
    logging.info("连接成功，并已获取初始数据。")
    return jsonify({"success": True, "departments": departments, "users": initial_users})

@app.route('/api/users/<int:dept_id>', methods=['GET'])
def get_users_by_department(dept_id):
    """根据部门ID获取用户，并进行内存分页"""
    logging.info(f"收到部门 [{dept_id}] 的用户查询请求...")
    # 从请求参数中获取页码和每页数量，提供默认值
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 15, type=int) # 默认每页15个

    token_read, error = get_access_token(session.get('corp_id'), session.get('app_secret'))
    if not token_read: 
        return jsonify({"success": False, "error": "会话过期或Token获取失败"})

    all_users, error = get_users_by_dept_api(token_read, dept_id)
    if error: 
        return jsonify({"success": False, "error": error})
        
    total_users = len(all_users)
    logging.info(f"部门 [{dept_id}] 全量用户数: {total_users}。正在进行分页处理: page={page}, limit={limit}")
    
    # 2. 计算分页切片
    start_index = (page - 1) * limit
    end_index = start_index + limit
    
    # 3. 获取当前页的用户数据
    paginated_users = all_users[start_index:end_index]
    
    # 4. 返回分页后的数据和总数
    return jsonify({
        "success": True, 
        "users": paginated_users,
        "total": total_users
    })
    
# 在 app.py 中找到 get_user_detail 函数，并用下面的代码完整替换它

@app.route('/api/user/<userid>', methods=['GET'])
def get_user_detail(userid):
    """获取单个用户详情，用于编辑"""
    logging.info(f"准备获取用户 [{userid}] 的非敏感信息用于编辑...")

    app_secret = session.get('app_secret')
    if not app_secret:
        return jsonify({"success": False, "error": "会话已过期，应用Secret丢失。"})

    # 使用应用Secret获取读取Token
    token_read, error = get_access_token(session.get('corp_id'), app_secret, token_type="应用")
    
    if not token_read:
        return jsonify({"success": False, "error": f"获取应用Token失败: {error}"})
    
    # 使用这个低权限Token去获取用户详情
    user_data, error = get_user_detail_api(token_read, userid)
    
    if error or user_data.get('errcode') != 0:
        error_msg = error or user_data.get('errmsg')
        logging.error(f"获取用户 [{userid}] 详细信息失败: {error_msg}")
        return jsonify({"success": False, "error": error_msg})
        
    logging.info(f"成功获取用户 [{userid}] 的非敏感信息。注意：手机号等字段因策略限制无法获取。")
    return jsonify({"success": True, "user": user_data})

@app.route('/api/user', methods=['POST', 'PUT', 'DELETE'])
def manage_user():
    token_write, error = get_access_token(session.get('corp_id'), session.get('txl_secret'), token_type="通讯录")
    if not token_write: return jsonify({"success": False, "error": "会话过期或通讯录Token获取失败"})
    result = {}
    if request.method == 'POST':
        user_data = request.json
        result = create_user_api(token_write, user_data)
    elif request.method == 'PUT':
        user_data = request.json
        result = update_user_api(token_write, user_data)
    elif request.method == 'DELETE':
        userid = request.json.get('userid')
        result = delete_user_api(token_write, userid)
    if result.get("errcode") == 0:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": result.get('errmsg', '未知错误')})

# --- 5. 启动应用 ---
if __name__ == '__main__':
    logging.info("启动 Flask Web 服务器...")
    app.run(host='0.0.0.0', port=5001)