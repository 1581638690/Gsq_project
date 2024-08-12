# 登录接口中解析出账号，关联token,其他接口通过token关联到账号输出到库里
import copy
import datetime
import re
from intell_analy_new_front_end import *


# 账户首先是需要进行获取 通过识别标注账户信息，提取token，来进行对照其他接口中的token进行关联账户信息

# 账户名 尽量中文标签尽量是账户名

def session_retrieval(user_dic, account_model, acc_o):
    """
    :param user_dic: 由Token作为键，账户信息作为值的字典
    :param result: 识别的标注数据
    :return:
    """

    result = read_model_identify(account_model, acc_o)
    data = result.get("data", {})
    user_infos = {}
    token_container = []
    account = ""
    if not data:
        return user_dic

    for http_pos, action_value in data.items():
        for action, value_lst in action_value.items():
            for name, value in value_lst.items():
                if name != "会话ID":
                    if len(value) >= 1:
                        user_infos[name] = value[0]
                else:
                    token_container = value
    user_infos["date"] = datetime.datetime.now()
    if token_container:
        for jsessionid in token_container:
            user_dic.setdefault(jsessionid, user_infos)
    return user_dic


def header_token_re(request_headers, keyword, user_info):
    """
    :param request_headers: 请求体
    :param keyword: 关键词
    :return:
    """
    token_container = {}
    sess_id = ""
    for i in request_headers:
        if i.get("name") == keyword:
            pattern = r"JSESSIONID=([A-Za-z0-9]+)"
            match = re.findall(pattern, i.get("value"))
            if len(match) > 1:

                for token in match:
                    if token in user_info:  # 如果存在与模型识别结果中
                        token_container = user_info[token]  # 获取用户信息
                    sess_id = token
    if token_container:
        del token_container["date"]
    return token_container


def header_token_model(keyword, user_info, account_model, acc_o):
    """
    :param request_headers: 请求体
    :param keyword: 关键词 会话ID
    :param user_info: 用户信息
    :return:
    """
    model_data = read_model_identify(account_model, acc_o)
    # 获取当前的token信息
    data = model_data.get("data", {})
    # current_token = ""
    user = {}
    sess_id = ""
    for pos, action_value in data.items():
        for action, value_lst in action_value.items():
            for name, value in value_lst.items():
                if name == keyword:
                    current_token = value[0] if len(value) > 1 else ""
                    if current_token and current_token in user_info:
                        user = user_info[current_token]
                        sess_id = current_token
    if user:
        del user["date"]
    return user, sess_id


def expiration_time(user_info):
    user_info = copy.deepcopy(user_info)
    remove_key = []
    new_date = datetime.datetime.now()
    for key, value in user_info.items():
        if (new_date - value.get("date")).total_seconds() // 3600 >= 12:
            remove_key.append(key)
            del user_info[key]
    for key in remove_key:
        del user_info[key]
    dump_pkl("/data/xlink/user_info.pkl", user_info)


if __name__ == '__main__':
    acc_o = {
        "app": app,
        "url": uri,
        'request_headers': o["http"]["request_headers"],
        "response_body": response_body
    }
