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
    sessid = ""
    account = ""
    result = read_model_identify(account_model, acc_o)
    label_info = result.get("label_info", {})
    if label_info.get("接口详情", "") == "登录":
        data = result.get("data", {})
        user_infos = {}
        token_container = []

        if not data:
            return user_dic, account

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
    else:
        # 获取到的是请求体中的 session_ID

        data = result.get("data", {})
        if data:
            for pos, pos_data in data.items():
                for action, action_data in pos_data.items():
                    for ch_name, value_list in action_data.items():
                        if ch_name == "会话ID" and value_list:
                            sessid = value_list[0]
    if sessid and sessid in user_dic:
        user_info = user_dic.get(sessid, {})
        account = user_info.get("账户名", "")
    return user_dic, account


def header_token_re(request_headers, response_headers, keyword, user_info):
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


def Refresh_cookie(request_headers, request_body, user_info):
    # 获取当前cookie信息
    token_container = {}
    sessid = ""
    current_sessid = ""
    user = {}
    for i in request_headers:
        if i.get("name") == "Cookie":
            pattern = r"JSESSIONID=([A-Za-z0-9]+)"
            match = re.findall(pattern, i.get("value"))
            if match:
                sessid = match[0]

    for i in request_body:
        if i.get("name") == "Set-Cookie":
            pattern = r"JSESSIONID=([A-Za-z0-9]+)"
            match = re.findall(pattern, i.get("value"))
            if match:
                current_sessid = match[0]
    if sessid and current_sessid:
        if sessid in user_info:
            # 获取到user信息
            token_container = user_info.get(sessid)
            # 添加 current_sessid到user_info
            user_info[current_sessid] = token_container
    elif sessid:
        if sessid in user_info:
            # 获取到user信息
            token_container = user_info.get(sessid)
    if token_container:
        user = copy.copy(token_container)
        del user["date"]
    return user, sessid


def Refresh_cookie1(request_headers, request_body, user_info):
    # 初始化变量
    sessid, current_sessid, user = "", "", {}
    token_container = {}

    # 预编译正则表达式
    jsessionid_pattern = re.compile(r"JSESSIONID=([A-Za-z0-9]+)")

    # 提取当前的 JSESSIONID
    for header in request_headers:
        if header.get("name") == "Cookie":
            match = jsessionid_pattern.search(header.get("value", ""))
            if match:
                sessid = match.group(1)
                break

    # 从响应体中提取新生成的 JSESSIONID
    for body_item in request_body:
        if body_item.get("name") == "Set-Cookie":
            match = jsessionid_pattern.search(body_item.get("value", ""))
            if match:
                current_sessid = match.group(1)
                break

    # 处理用户信息
    if sessid and current_sessid:
        # 更新 user_info 字典
        token_container = user_info.get(sessid, {})
        if token_container:
            user_info[current_sessid] = token_container
    elif sessid:
        # 仅查找旧的 sessid
        token_container = user_info.get(sessid, {})

    # 复制用户信息并移除日期信息
    if token_container:
        user = copy.deepcopy(token_container)
        user.pop("date", None)

    return user, sessid


if __name__ == '__main__':
    # acc_o = {
    #     "app": app,
    #     "url": uri,
    #     'request_headers': o["http"]["request_headers"],
    #     "response_body": response_body
    # }
    user_info = {
        "ED26D737511E2254AD25ED3B96D6369E": {"账户名": "徐君", "职位名称": "瑞成科技", "工作电话": "19137591556",
                                             "date": datetime.datetime(2024, 8, 15, 14, 13, 32, 319804)}
    }
    oolist = [
        {
            "request_headers": [{"name": "Host", "value": "59.202.68.95:8215"}, {"name": "Cookie",
                                                                                 "value": "JSESSIONID=ED26D737511E2254AD25ED3B96D6369E; wyhtml=/dataasset/_191496b3de2c211"}],
            "response_headers": [
                {"name": "Set-Cookie", 'value': "JSESSIONID=C40ACF409F5B006BD5DCFB09FFC77280"}
            ]},
        {
            "request_headers": [{"name": "Host", "value": "59.202.68.95:8215"}, {"name": "Cookie",
                                                                                 "value": "JSESSIONID=C40ACF409F5B006BD5DCFB09FFC77280; wyhtml=/dataasset/_191496b3de2c211"}],
            "response_headers": [
                {"name": "Server", "value": "nginx/1.24.0"}
            ]
        }
    ]
    for oo in oolist:
        request_headers = oo.get("request_headers")
        response_headers = oo.get("response_headers")
        user, sessid = Refresh_cookie1(request_headers, response_headers, user_info)
        print(user)
        print(sessid)

    o_list = {
        "con": {"": {"urld": {"msg": "http://10.96.8.167/api/login", "judge": "="}}},
        "datas": [
            {
                "data": {
                    "request_headers": [
                        {
                            "name": "Host",
                            "value": "10.96.8.167"
                        },
                        {
                            "name": "Connection",
                            "value": "keep-alive"
                        },
                        {
                            "name": "Content-Length",
                            "value": "50"
                        },
                        {
                            "name": "Accept",
                            "value": "application/json, text/plain, */*"
                        },
                        {
                            "name": "Authorization",
                            "value": "Bearer eyJhbGciOiJIUzUxMiJ9.eyJ1c2VySWQiOjE3NDI4NzgwMTg4NDg0MDM0NTcsImFjY291bnQiOiJ6aGVuZ3pob3VXTCIsInV1aWQiOiJjYzEyNmRhZi0wMDg5LTQ5NTQtOWZkYi1jYmU5MjRkOTQxOGEiLCJzdWIiOiIxNzQyODc4MDE4ODQ4NDAzNDU3IiwiaWF0IjoxNzIzNDIwNzc1LCJleHAiOjE3MjM1MDcxNzV9.-mxtOcHwlrO2WE5qRQTuE9rNSVoQ5m3GKg5OMOw-1Cy6gAxjp0PX578LKE0cTTTnO4BIeBAsWE02SpuRY8XvCA"
                        },
                        {
                            "name": "User-Agent",
                            "value": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
                        },
                        {
                            "name": "Content-Type",
                            "value": "application/json;charset=UTF-8"
                        },
                        {
                            "name": "Origin",
                            "value": "http://10.96.8.167"
                        },
                        {
                            "name": "Referer",
                            "value": "http://10.96.8.167/user/login?redirect=%2FunLoadingConditionAnalysis"
                        },
                        {
                            "name": "Accept-Encoding",
                            "value": "gzip, deflate"
                        },
                        {
                            "name": "Accept-Language",
                            "value": "zh-CN,zh;q=0.9"
                        }
                    ],
                    "response_headers": [
                        {
                            "name": "Server",
                            "value": "nginx/1.24.0"
                        },
                        {
                            "name": "Date",
                            "value": "Sun, 11 Aug 2024 23:59:39 GMT"
                        },
                        {
                            "name": "Content-Type",
                            "value": "application/json"
                        },
                        {
                            "name": "Transfer-Encoding",
                            "value": "chunked"
                        },
                        {
                            "name": "Connection",
                            "value": "keep-alive"
                        },
                        {
                            "name": "Vary",
                            "value": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                        },
                        {
                            "name": "Request-No",
                            "value": "9c4e2524-2578-43bb-aff4-a9d382b84dbd"
                        },
                        {
                            "name": "X-Content-Type-Options",
                            "value": "nosniff"
                        },
                        {
                            "name": "X-XSS-Protection",
                            "value": "1; mode=block"
                        },
                        {
                            "name": "Cache-Control",
                            "value": "no-cache, no-store, max-age=0, must-revalidate"
                        },
                        {
                            "name": "Pragma",
                            "value": "no-cache"
                        },
                        {
                            "name": "Expires",
                            "value": "0"
                        }
                    ],
                    "url": "http://10.96.8.167/api/login",
                    "request_body": {
                        "password": "Zzwl@123456",
                        "account": "zhengzhouWL"
                    },
                    "response_body": {
                        "success": True,
                        "code": 200,
                        "message": "请求成功",
                        "data": "eyJhbGciOiJIUzUxMiJ9.eyJ1c2VySWQiOjE3NDI4NzgwMTg4NDg0MDM0NTcsImFjY291bnQiOiJ6aGVuZ3pob3VXTCIsInV1aWQiOiIyZTQxYWJhMi02MWFiLTQ0ZmUtOWEwZi1jMjM5OTk4M2RmNDAiLCJzdWIiOiIxNzQyODc4MDE4ODQ4NDAzNDU3IiwiaWF0IjoxNzIzNDIwNzc5LCJleHAiOjE3MjM1MDcxNzl9.ryTeVJrr-sySC8K1wyG4qo8t2UujSjSxigzoJP6Xs8iD2MeuMJ5oojuWOS6WYwyCRf-EI5Zg6S3E35RFyYjCsw"
                    }
                },
                "idx": 0,
                "imps": [
                    {
                        "imp_type": "JSON",
                        "imp_data": "account",
                        "imp_name": ">>账户名",
                        "imp_pos": "request_body",
                        "imp_uid": "id-lzw1zt5y-at05zi97n"
                    },
                    {
                        "imp_type": "JSON",
                        "imp_data": "data",
                        "imp_name": ">>会话ID",
                        "imp_pos": "response_body",
                        "imp_uid": "id-lzw1zt5y-at05zi78n"
                    }
                ]
            }
        ]
    }
    acc = {
        "con": {
            "": {
                "app": {
                    "judge": "=",
                    "msg": "10.96.8.167"
                },
                "url": {
                    "judge": "!=",
                    "msg": "http://10.96.8.167/api/login"
                }
            }
        },
        "datas": [
            {
                "data": {
                    "time": "2024-08-16T17:35:55",
                    "app": "10.96.8.167",
                    "app_name": "Index of /theme",
                    "flow_id": "1624805946865125",
                    "urld": "http://100.78.76.36/ebus/00000000000_nw_dzfpfwpt/swjggl/dzfpXtQyxxwh/v1/selectLpkjQyxzByNsrsbh",
                    "name": "",
                    "account": "",
                    "url": "http://100.78.76.36/ebus/00000000000_nw_dzfpfwpt/swjggl/dzfpXtQyxxwh/v1/selectLpkjQyxzByNsrsbh",
                    "auth_type": 0,
                    "cls": "[]",
                    "levels": "",
                    "srcip": "98.7.152.8",
                    "real_ip": "98.7.128.63",
                    "dstip": "100.78.76.36",
                    "dstport": 80,
                    "http_method": "POST",
                    "status": 200,
                    "api_type": "5",
                    "risk_level": "0",
                    "qlength": 0,
                    "yw_count": 0,
                    "length": "0",
                    "age": 21556,
                    "srcport": 54724,
                    "parameter": "",
                    "content_length": 165,
                    "id": "1723800955175370323",
                    "content_type": "JSON",
                    "key": "\"\"",
                    "info": "{}",
                    "request_headers": "[{\"name\":\"X-Stgw-Time\",\"value\":\"1679104588.855, 1679104590.515\"},{\"name\":\"X-Client-Proto\",\"value\":\"http, http\"},{\"name\":\"X-Forwarded-Proto\",\"value\":\"http, http\"},{\"name\":\"X-Client-Proto-Ver\",\"value\":\"HTTP\\/1.1, HTTP\\/1.1\"},{\"name\":\"X-Real-IP\",\"value\":\"98.7.128.63, 98.7.152.32\"},{\"name\":\"X-Forwarded-For\",\"value\":\"98.7.128.63,98.7.128.63, 98.7.152.25,98.7.152.25, 10.114.128.90,10.114.128.90, 10.114.152.7,10.114.152.7,127.0.0.1, 10.114.152.2,98.7.152.32, 98.7.152.12,98.7.152.12\"},{\"name\":\"Content-Length\",\"value\":\"402\"},{\"name\":\"TSF-Metadata\",\"value\":\"{\\\"ai\\\":\\\"application-m6yomnvl\\\",\\\"av\\\":\\\"master-pro-20230215-145130\\\",\\\"sn\\\":\\\"swjggl-service\\\",\\\"ii\\\":\\\"scsj-swjggl-service-6d4579bd7b-98l5x\\\",\\\"gi\\\":\\\"group-ldap7gao\\\",\\\"li\\\":\\\"172.16.19.4\\\",\\\"ni\\\":\\\"namespace-jnygw5v2\\\"}, {\\\"ai\\\":\\\"application-l6yme2vg\\\",\\\"av\\\":\\\"master-pro-20230224-091226\\\",\\\"sn\\\":\\\"ypfw-ctrl-nsrd\\\",\\\"ii\\\":\\\"scsj-ypfw-ctrl-nsrd-6975d4467d-5zk52\\\",\\\"gi\\\":\\\"group-gnalxgaq\\\",\\\"li\\\":\\\"172.16.21.124\\\",\\\"ni\\\":\\\"namespace-jqv3z9y7\\\"}\"},{\"name\":\"tran_seq\",\"value\":\"589818a955474a3cbc1478be2ae5ddbf, e988e4a313164da3be313b88af8b6f70\"},{\"name\":\"x-tif-timestamp\",\"value\":\"1679104588, 1679104591\"},{\"name\":\"X-B3-ParentSpanId\",\"value\":\"ee70659b4b8246c1, 04b11b22fb2db4a1\"},{\"name\":\"x-tif-paasid\",\"value\":\"15000000000_nw_sjdpfp, 15000000000_ww_dzfpfwptww\"},{\"name\":\"x-tif-signature\",\"value\":\"c75db7b7921b97fe783e439dfa471bbc6faeb8248a99a6200f2a94cc3e44841b, 0C28AAAD2BA070E58F726D8BE855E3360D00E5F91F243292DC1326235671A285\"},{\"name\":\"X-B3-SpanId\",\"value\":\"26fc096d5faeeb01, c31c385b22417128\"},{\"name\":\"css-header-sso\",\"value\":\"{\\\"sessionId\\\":\\\"8822240d244042c58c26081e8f73d042\\\",\\\"userId\\\":0,\\\"orgId\\\":0,\\\"channelId\\\":0,\\\"systemData\\\":{\\\"SSOTicket\\\":\\\"dd54b92e145b47cda0cbdafee25a87fd\\\"},\\\"bizData\\\":{\\\"enterprise_type\\\":\\\"0\\\",\\\"mainIdentity\\\":\\\"1\\\",\\\"birthdate\\\":\\\"\\\",\\\"security-bad-type\\\":\\\"0\\\",\\\"login_type\\\":\\\"2\\\",\\\"endDate\\\":\\\"\\\",\\\"trust_code\\\":\\\"92500119MAABQKP514\\\",\\\"tax_authority_code\\\":\\\"15003842100\\\",\\\"swjgmc\\\":\\\"POST \\/ebus\\/00000000000_nw_dzfpfwpt\\/yp\\/bdkgx\\/v1\\/zzsfpxxcx HTTP\\/1.1\"},{\"name\":\"Accept\",\"value\":\"application\\/json\"},{\"name\":\"Authorization\",\"value\":\"Bearer eyJhbGciOiJIUzUxMiJ9.eyJ1c2VySWQiOjE3NDI4NzgwMTg4NDg0MDM0NTcsImFjY291bnQiOiJ6aGVuZ3pob3VXTCIsInV1aWQiOiIyZTQxYWJhMi02MWFiLTQ0ZmUtOWEwZi1jMjM5OTk4M2RmNDAiLCJzdWIiOiIxNzQyODc4MDE4ODQ4NDAzNDU3IiwiaWF0IjoxNzIzNDIwNzc5LCJleHAiOjE3MjM1MDcxNzl9.ryTeVJrr-sySC8K1wyG4qo8t2UujSjSxigzoJP6Xs8iD2MeuMJ5oojuWOS6WYwyCRf-EI5Zg6S3E35RFyYjCsw\"}]",
                    "response_headers": "[{\"name\":\"Date\",\"value\":\"Sat, 18 Mar 2023 01:56:28 GMT\"},{\"name\":\"Content-Type\",\"value\":\"application\\/json;charset=UTF-8\"},{\"name\":\"Transfer-Encoding\",\"value\":\"chunked\"},{\"name\":\"Connection\",\"value\":\"keep-alive\"},{\"name\":\"x-proxy-by\",\"value\":\"Tif-APIGate\"},{\"name\":\"x-forwarded-for\",\"value\":\"100.78.0.158,127.0.0.1,100.78.76.41\"},{\"name\":\"set-cookie\",\"value\":\"x_host_key=186f26ebc8a-376d03f1ece7d1b0749d91564afa71cf6783b54b; path=\\/; HttpOnly\"}]",
                    "request_body": "",
                    "response_body": "{\"Response\":{\"RequestId\":\"d4a104aa1eacd069\",\"Error\":{\"Code\":\"GT4000102223009\",\"Message\":\"该企业税号不是稀土企业，无法发开具\"},\"Data\":0}}"
                },
                "imps": [
                    {
                        "imp_type": "TEXT",
                        "imp_data": "eyJhbGciOiJIUzUxMiJ9.eyJ1c2VySWQiOjE3NDI4NzgwMTg4NDg0MDM0NTcsImFjY291bnQiOiJ6aGVuZ3pob3VXTCIsInV1aWQiOiIyZTQxYWJhMi02MWFiLTQ0ZmUtOWEwZi1jMjM5OTk4M2RmNDAiLCJzdWIiOiIxNzQyODc4MDE4ODQ4NDAzNDU3IiwiaWF0IjoxNzIzNDIwNzc5LCJleHAiOjE3MjM1MDcxNzl9.ryTeVJrr-sySC8K1wyG4qo8t2UujSjSxigzoJP6Xs8iD2MeuMJ5oojuWOS6WYwyCRf-EI5Zg6S3E35RFyYjCsw",
                        "imp_name": "地址信息-L1>>会话ID",
                        "imp_pos": "request_headers",
                        "imp_uid": "id-lzwimf0o-o2ko3vg4d"
                    }
                ],
                "idx": 0
            }
        ]
    }
    # 现在需要对登录接口进行标注吧
    con = acc.get("con")
    datas = acc.get("datas")
    intell_rule = handle_project(con, datas)
    print(intell_rule)
    rules = {'': {'>>账户名': {'JSONid-lzw1zt5y-at05zi97n_0': {'request_body': ['account']}},
                  '>>会话ID': {'JSONid-lzw1zt5y-at05zi78n_1': {'response_body': ['data']}}}}
    models_data = {
        "登录接口": {"rules": {'>>账户名': {'JSONid-lzw1zt5y-at05zi97n_0': {'request_body': ['account']}},
                               '>>会话ID': {'JSONid-lzw1zt5y-at05zi78n_1': {'response_body': ['data']}}},
                     "condition": {"urld": {"msg": "http://10.96.8.167/api/login", "judge": "="}},
                     "label_info": {"接口详情": "登录"}
                     },
        "账户获取": {"rules": {'地址信息-L1>>会话ID': {'id-lzwimf0o-o2ko3vg4d_0': {
            'request_headers': {'Authorization': {'start': {'str': 'Bearer '}, 'end': {}}}}}},
            "condition": {"app": {"msg": "10.96.8.167", "judge": "="},"urld": {
                    "judge": "!=",
                    "msg": "http://10.96.8.167/api/login"
                }},
            "label_info": {}
        }
    }
    ooo = [
        {
            "app": "10.96.8.167",
            "request_headers": [
                {
                    "name": "Host",
                    "value": "10.96.8.167"
                },
                {
                    "name": "Connection",
                    "value": "keep-alive"
                },
                {
                    "name": "Content-Length",
                    "value": "50"
                },
                {
                    "name": "Accept",
                    "value": "application/json, text/plain, */*"
                },
                {
                    "name": "Authorization",
                    "value": "Bearer eyJhbGciOiJIUzUxMiJ9.eyJ1c2VySWQiOjE3NDI4NzgwMTg4NDg0MDM0NTcsImFjY291bnQiOiJ6aGVuZ3pob3VXTCIsInV1aWQiOiJjYzEyNmRhZi0wMDg5LTQ5NTQtOWZkYi1jYmU5MjRkOTQxOGEiLCJzdWIiOiIxNzQyODc4MDE4ODQ4NDAzNDU3IiwiaWF0IjoxNzIzNDIwNzc1LCJleHAiOjE3MjM1MDcxNzV9.-mxtOcHwlrO2WE5qRQTuE9rNSVoQ5m3GKg5OMOw-1Cy6gAxjp0PX578LKE0cTTTnO4BIeBAsWE02SpuRY8XvCA"
                },
                {
                    "name": "User-Agent",
                    "value": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
                },
                {
                    "name": "Content-Type",
                    "value": "application/json;charset=UTF-8"
                },
                {
                    "name": "Origin",
                    "value": "http://10.96.8.167"
                },
                {
                    "name": "Referer",
                    "value": "http://10.96.8.167/user/login?redirect=%2FunLoadingConditionAnalysis"
                },
                {
                    "name": "Accept-Encoding",
                    "value": "gzip, deflate"
                },
                {
                    "name": "Accept-Language",
                    "value": "zh-CN,zh;q=0.9"
                }
            ],
            "response_headers": [
                {
                    "name": "Server",
                    "value": "nginx/1.24.0"
                },
                {
                    "name": "Date",
                    "value": "Sun, 11 Aug 2024 23:59:39 GMT"
                },
                {
                    "name": "Content-Type",
                    "value": "application/json"
                },
                {
                    "name": "Transfer-Encoding",
                    "value": "chunked"
                },
                {
                    "name": "Connection",
                    "value": "keep-alive"
                },
                {
                    "name": "Vary",
                    "value": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                },
                {
                    "name": "Request-No",
                    "value": "9c4e2524-2578-43bb-aff4-a9d382b84dbd"
                },
                {
                    "name": "X-Content-Type-Options",
                    "value": "nosniff"
                },
                {
                    "name": "X-XSS-Protection",
                    "value": "1; mode=block"
                },
                {
                    "name": "Cache-Control",
                    "value": "no-cache, no-store, max-age=0, must-revalidate"
                },
                {
                    "name": "Pragma",
                    "value": "no-cache"
                },
                {
                    "name": "Expires",
                    "value": "0"
                }
            ],
            "urld": "http://10.96.8.167/api/login",
            "request_body": {
                "password": "Zzwl@123456",
                "account": "zhengzhouWL"
            },
            "response_body": {
                "success": True,
                "code": 200,
                "message": "请求成功",
                "data": "eyJhbGciOiJIUzUxMiJ9.eyJ1c2VySWQiOjE3NDI4NzgwMTg4NDg0MDM0NTcsImFjY291bnQiOiJ6aGVuZ3pob3VXTCIsInV1aWQiOiIyZTQxYWJhMi02MWFiLTQ0ZmUtOWEwZi1jMjM5OTk4M2RmNDAiLCJzdWIiOiIxNzQyODc4MDE4ODQ4NDAzNDU3IiwiaWF0IjoxNzIzNDIwNzc5LCJleHAiOjE3MjM1MDcxNzl9.ryTeVJrr-sySC8K1wyG4qo8t2UujSjSxigzoJP6Xs8iD2MeuMJ5oojuWOS6WYwyCRf-EI5Zg6S3E35RFyYjCsw"
            }
        },
        {
            "time": "2024-08-16T17:35:55",
            "app": "10.96.8.167",
            "app_name": "Index of /theme",
            "flow_id": "1624805946865125",
            "urld": "http://100.78.76.36/ebus/00000000000_nw_dzfpfwpt/swjggl/dzfpXtQyxxwh/v1/selectLpkjQyxzByNsrsbh",
            "name": "",
            "account": "",
            "url": "http://100.78.76.36/ebus/00000000000_nw_dzfpfwpt/swjggl/dzfpXtQyxxwh/v1/selectLpkjQyxzByNsrsbh",
            "auth_type": 0,
            "cls": "[]",
            "levels": "",
            "srcip": "98.7.152.8",
            "real_ip": "98.7.128.63",
            "dstip": "100.78.76.36",
            "dstport": 80,
            "http_method": "POST",
            "status": 200,
            "api_type": "5",
            "risk_level": "0",
            "qlength": 0,
            "yw_count": 0,
            "length": "0",
            "age": 21556,
            "srcport": 54724,
            "parameter": "",
            "content_length": 165,
            "id": "1723800955175370323",
            "content_type": "JSON",
            "key": "\"\"",
            "info": "{}",
            "request_headers": "[{\"name\":\"X-Stgw-Time\",\"value\":\"1679104588.855, 1679104590.515\"},{\"name\":\"X-Client-Proto\",\"value\":\"http, http\"},{\"name\":\"X-Forwarded-Proto\",\"value\":\"http, http\"},{\"name\":\"X-Client-Proto-Ver\",\"value\":\"HTTP\\/1.1, HTTP\\/1.1\"},{\"name\":\"X-Real-IP\",\"value\":\"98.7.128.63, 98.7.152.32\"},{\"name\":\"X-Forwarded-For\",\"value\":\"98.7.128.63,98.7.128.63, 98.7.152.25,98.7.152.25, 10.114.128.90,10.114.128.90, 10.114.152.7,10.114.152.7,127.0.0.1, 10.114.152.2,98.7.152.32, 98.7.152.12,98.7.152.12\"},{\"name\":\"Content-Length\",\"value\":\"402\"},{\"name\":\"TSF-Metadata\",\"value\":\"{\\\"ai\\\":\\\"application-m6yomnvl\\\",\\\"av\\\":\\\"master-pro-20230215-145130\\\",\\\"sn\\\":\\\"swjggl-service\\\",\\\"ii\\\":\\\"scsj-swjggl-service-6d4579bd7b-98l5x\\\",\\\"gi\\\":\\\"group-ldap7gao\\\",\\\"li\\\":\\\"172.16.19.4\\\",\\\"ni\\\":\\\"namespace-jnygw5v2\\\"}, {\\\"ai\\\":\\\"application-l6yme2vg\\\",\\\"av\\\":\\\"master-pro-20230224-091226\\\",\\\"sn\\\":\\\"ypfw-ctrl-nsrd\\\",\\\"ii\\\":\\\"scsj-ypfw-ctrl-nsrd-6975d4467d-5zk52\\\",\\\"gi\\\":\\\"group-gnalxgaq\\\",\\\"li\\\":\\\"172.16.21.124\\\",\\\"ni\\\":\\\"namespace-jqv3z9y7\\\"}\"},{\"name\":\"tran_seq\",\"value\":\"589818a955474a3cbc1478be2ae5ddbf, e988e4a313164da3be313b88af8b6f70\"},{\"name\":\"x-tif-timestamp\",\"value\":\"1679104588, 1679104591\"},{\"name\":\"X-B3-ParentSpanId\",\"value\":\"ee70659b4b8246c1, 04b11b22fb2db4a1\"},{\"name\":\"x-tif-paasid\",\"value\":\"15000000000_nw_sjdpfp, 15000000000_ww_dzfpfwptww\"},{\"name\":\"x-tif-signature\",\"value\":\"c75db7b7921b97fe783e439dfa471bbc6faeb8248a99a6200f2a94cc3e44841b, 0C28AAAD2BA070E58F726D8BE855E3360D00E5F91F243292DC1326235671A285\"},{\"name\":\"X-B3-SpanId\",\"value\":\"26fc096d5faeeb01, c31c385b22417128\"},{\"name\":\"css-header-sso\",\"value\":\"{\\\"sessionId\\\":\\\"8822240d244042c58c26081e8f73d042\\\",\\\"userId\\\":0,\\\"orgId\\\":0,\\\"channelId\\\":0,\\\"systemData\\\":{\\\"SSOTicket\\\":\\\"dd54b92e145b47cda0cbdafee25a87fd\\\"},\\\"bizData\\\":{\\\"enterprise_type\\\":\\\"0\\\",\\\"mainIdentity\\\":\\\"1\\\",\\\"birthdate\\\":\\\"\\\",\\\"security-bad-type\\\":\\\"0\\\",\\\"login_type\\\":\\\"2\\\",\\\"endDate\\\":\\\"\\\",\\\"trust_code\\\":\\\"92500119MAABQKP514\\\",\\\"tax_authority_code\\\":\\\"15003842100\\\",\\\"swjgmc\\\":\\\"POST \\/ebus\\/00000000000_nw_dzfpfwpt\\/yp\\/bdkgx\\/v1\\/zzsfpxxcx HTTP\\/1.1\"},{\"name\":\"Accept\",\"value\":\"application\\/json\"},{\"name\":\"Authorization\",\"value\":\"Bearer eyJhbGciOiJIUzUxMiJ9.eyJ1c2VySWQiOjE3NDI4NzgwMTg4NDg0MDM0NTcsImFjY291bnQiOiJ6aGVuZ3pob3VXTCIsInV1aWQiOiIyZTQxYWJhMi02MWFiLTQ0ZmUtOWEwZi1jMjM5OTk4M2RmNDAiLCJzdWIiOiIxNzQyODc4MDE4ODQ4NDAzNDU3IiwiaWF0IjoxNzIzNDIwNzc5LCJleHAiOjE3MjM1MDcxNzl9.ryTeVJrr-sySC8K1wyG4qo8t2UujSjSxigzoJP6Xs8iD2MeuMJ5oojuWOS6WYwyCRf-EI5Zg6S3E35RFyYjCsw\"}]",
            "response_headers": "[{\"name\":\"Date\",\"value\":\"Sat, 18 Mar 2023 01:56:28 GMT\"},{\"name\":\"Content-Type\",\"value\":\"application\\/json;charset=UTF-8\"},{\"name\":\"Transfer-Encoding\",\"value\":\"chunked\"},{\"name\":\"Connection\",\"value\":\"keep-alive\"},{\"name\":\"x-proxy-by\",\"value\":\"Tif-APIGate\"},{\"name\":\"x-forwarded-for\",\"value\":\"100.78.0.158,127.0.0.1,100.78.76.41\"},{\"name\":\"set-cookie\",\"value\":\"x_host_key=186f26ebc8a-376d03f1ece7d1b0749d91564afa71cf6783b54b; path=\\/; HttpOnly\"}]",
            "request_body": "",
            "response_body": "{\"Response\":{\"RequestId\":\"d4a104aa1eacd069\",\"Error\":{\"Code\":\"GT4000102223009\",\"Message\":\"该企业税号不是稀土企业，无法发开具\"},\"Data\":0}}"
        }
    ]
    user_dic = {}
    for o in ooo:
        user_dic, account = session_retrieval(user_dic, models_data, o)
        print(user_dic)
        print(account)

    'eyJhbGciOiJIUzUxMiJ9.eyJ1c2VySWQiOjE3NDI4NzgwMTg4NDg0MDM0NTcsImFjY291bnQiOiJ6aGVuZ3pob3VXTCIsInV1aWQiOiJjYzEyNmRhZi0wMDg5LTQ5NTQtOWZkYi1jYmU5MjRkOTQxOGEiLCJzdWIiOiIxNzQyODc4MDE4ODQ4NDAzNDU3IiwiaWF0IjoxNzIzNDIwNzc1LCJleHAiOjE3MjM1MDcxNzV9.-mxtOcHwlrO2WE5qRQTuE9rNSVoQ5m3GKg5OMOw-1Cy6gAxjp0PX578LKE0cTTTnO4BIeBAsWE02SpuRY8XvCA'
    "eyJhbGciOiJIUzUxMiJ9.eyJ1c2VySWQiOjE3NDI4NzgwMTg4NDg0MDM0NTcsImFjY291bnQiOiJ6aGVuZ3pob3VXTCIsInV1aWQiOiIyZTQxYWJhMi02MWFiLTQ0ZmUtOWEwZi1jMjM5OTk4M2RmNDAiLCJzdWIiOiIxNzQyODc4MDE4ODQ4NDAzNDU3IiwiaWF0IjoxNzIzNDIwNzc5LCJleHAiOjE3MjM1MDcxNzl9.ryTeVJrr-sySC8K1wyG4qo8t2UujSjSxigzoJP6Xs8iD2MeuMJ5oojuWOS6WYwyCRf-EI5Zg6S3E35RFyYjCsweyJhbGciOiJIUzUxMiJ9.eyJ1c2VySWQiOjE3NDI4NzgwMTg4NDg0MDM0NTcsImFjY291bnQiOiJ6aGVuZ3pob3VXTCIsInV1aWQiOiIyZTQxYWJhMi02MWFiLTQ0ZmUtOWEwZi1jMjM5OTk4M2RmNDAiLCJzdWIiOiIxNzQyODc4MDE4ODQ4NDAzNDU3IiwiaWF0IjoxNzIzNDIwNzc5LCJleHAiOjE3MjM1MDcxNzl9.ryTeVJrr-sySC8K1wyG4qo8t2UujSjSxigzoJP6Xs8iD2MeuMJ5oojuWOS6WYwyCRf-EI5Zg6S3E35RFyYjCsw"
