#!/usr/bin/python
# -*- coding: utf-8 -*-
import shutil
import sys
import configparser
import requests
import ujson

# 读取配置文件
path_config = configparser.ConfigParser()
# path_config.read('config_window.ini')
path_config.read('/opt/openfbi/pylibs/config.ini')
# 获取路径
xlink_base_path = path_config['paths']['xlink_base_path']

sys.path.append("lib")
from bottle import request, route, response, redirect as redirect1
import json
import zipfile
from avenger.fsys import *
from avenger.fssdb import *
from avenger.fastbi import compile_fbi
from avenger.fglobals import *
from avenger.fio import *
from avenger.fbiobject import FbiEngMgr

ssdb0 = fbi_global.get_ssdb0()
# 引擎管理
fbi_eng_mgr = FbiEngMgr(ssdb0)
# 用户管理
fbi_user_mgr = FbiUserMgr(ssdb0)

sys.path.append("/opt/openfbi/pylibs")
from intell_analy_new import *


@route('/test')
def get_test():
    return "你好，测试成功!"


@route("/cls_d", method="POST")
def get_clssify():
    """
    获取前端传入的三条日志信息，返回分类上下文规则给前端
    :return:
    """
    # 接口后的参数信息 , body raw直接传入 数据 {“datas”:[{},{},{}]}
    try:
        datas = request.json
        o_data = datas.get("datas", {})

        result = clas_data(o_data)

        return {"status": "Success", "cls_res": result}
    except Exception as e:
        return {"status": "Error", "msg": str(e)}


def clas_data(datass):
    res = {}
    con_res = {}
    for o_data in datass:
        for key, value in o_data.items():
            # 忽略空值
            if not value:
                continue

            # 直接将键后面全部跟上列表
            res.setdefault(key, []).append(value)
    for key, value in res.items():
        # 判断键对应的值的类型
        if len(value) == 1:
            con_res = condition_judge(value, key, con_res)
        elif len(value) > 1:
            con_res = condition_judge(value, key, con_res, is_list=True)
    return con_res


def condition_judge(value, key, res, is_list=False):
    if len(value) == 1:
        if is_list:
            res.setdefault(key, {}).setdefault("judge", "in")
            res.setdefault(key, {}).setdefault("msg", value)
        else:
            res.setdefault(key, {}).setdefault("judge", "=")
            res.setdefault(key, {}).setdefault("msg", value[0])
    elif len(value) > 1:
        res.setdefault(key, {}).setdefault("judge", "in")
        res.setdefault(key, {}).setdefault("msg", value)
    return res


@route("/con_q", method="POST")  # 上下文规则传递
def query_save():
    """
    :return: 获取经过人工处理过的分类信息
    """
    try:
        query_json = request.json
        query_name = query_json.get("query_name", "")  # 获取上下文规则名称
        condition = query_json.get("con", "")  #
        json_key = ujson.dumps(condition)
        return {"status": "Success", "con": {query_name: json_key}}
    except Exception as e:
        return {"status": "Error", "msg": str(e)}


@route("/als_d", method="POST")
def intell_analysis():
    """
    智能分析接口,进行提取分析数据
    :return:
    """
    try:
        output_res = {}
        q_d = request.json  # 获取到前端发来的消息 其中包括上下文规则信息，标识的数据信息
        datas = q_d["datas"]  # 获取标识信息
        con = q_d["con"]  # 获取上下文规则信息
        # 获取需要形成规则的数据信息
        # label_data = datas["datas"]
        # 获取初始化或者 传递函数的规则信息
        # rules = datas["rules"]

        # 获取相应规则，目前按照1条规则进行测试
        try:
            intell_rule = handle_project(con, datas)  # 如果传入一条 则是返回一条，但是该条不能直接写入规则文件中，因为还需要判断识别是否为空
            print(intell_rule)
            # print(con)
        except Exception as e:
            return {"status": "Error", "msg": f"规则提取失败:{e.__str__()}"}
        # 根据获取出的规则进行识别我们这三条信息，将数据传递给前端界面
        try:
            idx_message = an_data(datas, intell_rule, con)
        except Exception as e:
            # idx_message={}
            return {"status": "Error", "msg": f"数据识别失败:{e.__str__()}"}
        if idx_message:
            # 根据规则名称 获取规则名

            output_res.setdefault("outcome", idx_message)
        else:
            output_res.setdefault("outcome", {})

        for model_key, da in con.items():
            output_res.setdefault("model_key", model_key)
            output_res.setdefault("con", da)
            if intell_rule:
                output_res.setdefault("rules", intell_rule[model_key])
            else:
                output_res.setdefault("rules", {})
        return {"status": "Success", "res": output_res}
    except Exception as e:
        return {"status": "Error", "res": str(e)}


@route("/s_rules_con", method="POST")
def rules_save():
    # 保存规则信息
    # 获取前端的规则数据，写入文件中
    try:
        crlf_add_alter = request.json  # 获取add_alter 修改的和新增内容
        add_data = crlf_add_alter.get("add", {})
        alter_data = crlf_add_alter.get("alter", {})
        file_str = crlf_add_alter.get("file_str", "")
    except Exception as e:
        return {"status": "Error", "msg": f"获取前台数据失败:{e.__str__()}"}
    if file_str == "":
        return {"status": "Error", "msg": "模型文件不能为空"}
    # 读取文件信息
    # 拼接文件路径
    # base_dir = "/data/xlink/models_paths/"
    # base_dir = "./"
    base_dir = path_config['paths']['store_base_dir']
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)

    source_file = os.path.join(base_dir, f"{file_str}_rcl_bak.pkl")
    destination_file = os.path.join(base_dir, f"{file_str}_rcl.pkl")
    tol_rulers = load_data(destination_file)
    add_msg = ""
    alter_msg = ""
    # 根据文件数据 进行增加修改规则
    if add_data:
        rules = add_data.get("rules", {})
        con = add_data.get("con", {})
        linfo = add_data.get("linfo", {})
        model_key = add_data.get("model_key", "")
        con = con.get(model_key, {})
        # 先将两者写入 到副本文件中，如果存在报错信息，则删除副本文件，返回错误信息
        try:
            tol_rulers = add_all_data(rules, con, model_key, linfo, tol_rulers)
            add_msg = f"新增模型成功！"
        except Exception as e:
            return {"status": "Error", "msg": f"子模型新增错误:{e.__str__()}"}
    if alter_data:
        rules = alter_data.get("rules", {})
        con = alter_data.get("con", {})
        linfo = alter_data.get("linfo", {})
        model_key = alter_data.get("model_key", "")
        old_key = alter_data.get("orl_key", "")
        con = con.get(model_key, {})
        try:
            tol_rulers = alter_all_data(rules, con, model_key, linfo, old_key, tol_rulers)
            alter_msg = f"修改模型成功！"
        except Exception as e:
            return {"status": "Error", "msg": f"子模型修改错误:{e.__str__()}"}
    res = write_replace(source_file, destination_file, tol_rulers)

    res.update({"add_msg": add_msg, "alter_msg": alter_msg})

    return res


@route("/delete_rulers", method="POST")
def delete_rules():
    # 删除子模型数据信息
    crlf = request.json
    model_key = crlf.get("model_key", {})
    file_str = crlf.get("file_str", "")
    res = delete_rules_data(model_key, file_str)
    return res


# 创建xlink，表信息，存储路径文件 一一对应
@route("/xlink_table_path", method="POST")
def xtp_create():
    """
    获取路径名称
    :return: 创建好的xlink_ID,表名，路径名称

    """
    path_name = request.params.get("p_name")
    try:
        res = found_path(path_name)
        return res
    except Exception as e:
        return {"status": "Error", "msg": f"创建模型时出现错误:{e.__str__()}"}


#             ##################add rzc 2024/4/28#####################
@route("/model_upload", method="POST")
def upload_models():
    """
    上传模型接口，要将模型文件，上传至当前环境下
    :return:
    """
    try:
        extract_base_dir = path_config['paths']['extract_base_dir']  # 解压路径
        base_dir = path_config['paths']['store_base_dir']  # 基础路径
        #  判断解压路径存不存在
        if not os.path.isdir(extract_base_dir):
            os.makedirs(extract_base_dir)
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)
        #  获取当前查询分析得模型名称
        file_str = request.params.get("file_str", "")  # 传入的是 当前模型的文件名
        # 对参数进行解码
        decoded_file_str = file_str
        # 获取上传的文件
        upload_file = request.files.get("file")
        if not upload_file:
            return ujson.dumps({"status": "Error", "msg": "未提供文件或文件名"}, ensure_ascii=False)

        # 获取文件压缩包原名称
        filename = upload_file.raw_filename

        # 拼接路径名称
        zip_filepath = os.path.join(extract_base_dir, filename)
        upload_file.save(zip_filepath, overwrite=True)  # 保存 默认覆盖文件信息

        # 解压缩文件
        try:
            with zipfile.ZipFile(zip_filepath, 'r') as zip_ref:
                zip_ref.extractall(extract_base_dir)
        except Exception as e:
            return ujson.dumps({"status": "Error", "msg": f"解压模型文件出错：{e.__str__()}"}, ensure_ascii=False)

        # 判断文件信息 然后进行读取返回给前端信息
        # 每次只能给一个智能模型 文件下面是三个文件
        extracted_files = os.listdir(extract_base_dir)
        cur_data = []
        res = {}
        #  默认等于三的时候才是正确的
        if len(extracted_files) == 3:
            for file in extracted_files:
                if file.endswith('.zip'):
                    continue
                elif file.endswith(".pkl"):
                    if "ui_data" in file:
                        # 需要返回的数据
                        # 读取该文件就行
                        with open(os.path.join(extract_base_dir, file), 'rb') as fp:
                            cur_data = pickle.load(fp)

                    else:
                        # 模型信息,如果 文件存在 就进行读取，如果不存在就写入
                        res = up_file_model(os.path.join(extract_base_dir, file), decoded_file_str, base_dir)
                        if res.get("status") == "Error":
                            shutil.rmtree(extract_base_dir)
                            return ujson.dumps(res, ensure_ascii=False)
                else:
                    shutil.rmtree(extract_base_dir)
                    return ujson.dumps({"status": "Error", "msg": f"路径文件异常，请重新上传模型文件！"},
                                       ensure_ascii=False)
            # 也需要清空
            shutil.rmtree(extract_base_dir)
            return ujson.dumps({"status": "Success", "data": cur_data, "model_info": res}, ensure_ascii=False)
        else:
            # 清空路径下面文件 重新上传模型
            shutil.rmtree(extract_base_dir)
            return ujson.dumps({"status": "Error", "msg": f"路径文件异常，请重新上传模型文件！"}, ensure_ascii=False)
    except Exception as e:
        return f"错误：f{e.__str__()}"


@route('/model_download', method='POST')
def models_download():
    """
    下载模型文件路由
    :param filename: 文件名
    :return:
    """
    try:
        # 设置文件存储路径
        file_str = request.json.get('filename', "")
        current_data = request.json.get('current_data', [])
        if not file_str:
            return {"status": "Error", "msg": "未提供文件名"}

        base_dir = path_config['paths']['store_base_dir']

        download_base_dir = path_config['paths']['download_base_dir']

        if not os.path.exists(base_dir):
            os.makedirs(base_dir)

        filename = file_str + "_rcl.pkl"

        ui_file = f"{file_str}_ui_data.pkl"
        # 将数据写入.pkl文件
        new_file_path = os.path.join(base_dir, ui_file)
        try:
            with open(new_file_path, 'wb') as f:
                pickle.dump(current_data, f)
        except Exception as e:
            return {"status": "Error", "msg": f"子模型列表导出失败：{e.__str__()}"}
        # 创建压缩文件信息
        zip_filename = f"{file_str}_rcl.zip"
        zip_file_path = os.path.join(base_dir, zip_filename)

        with zipfile.ZipFile(zip_file_path, "w") as zipf:
            zipf.write(new_file_path, ui_file)
            zipf.write(base_dir + filename, filename)
        #  将zip_file_path 移动到workspace下面
        if not os.path.exists(download_base_dir):
            os.makedirs(download_base_dir)
        workspace_path = os.path.join(download_base_dir, zip_filename)
        try:
            shutil.move(zip_file_path, workspace_path)
            # 删除 子模型列表信息
            os.remove(new_file_path)
        except Exception as e:
            return {"status": "Error", "msg": f"移动文件出错：{e.__str__()}"}
        response.content_type = 'application/zip'

        return {"status": "Success", "download_link": workspace_path}

    except Exception as e:
        return {"status": "Error", "msg": f"错误：{e.__str__()}"}


clientID = "qllsj"
clientSecret = "5ca6d687b49f4a1cae1aeaa4aa286991"
AUTHORIZATION_URL = 'https://iam.gongshu.gov.cn/idp/authCenter/authenticate'
redirect_uri = "https://59.202.68.91:8443/db/auth3"
github_auth_url = f"{AUTHORIZATION_URL}?response_type=code&state=1&redirect_uri={redirect_uri}&client_id={clientID}"

@route('/rlogin')
def authenticate():
    client_id = request.query.client_id or clientID
    redirect_url = request.query.redirect_uri or redirect_uri
    response_type = request.query.response_type or 'code'
    state = request.query.state or '1'
    if not client_id or client_id != clientID:
        # return {'errcode': 400, 'msg': 'Invalid or missing client_id'}
        return redirect1("https://iam.gongshu.gov.cn/login/")
    if not redirect_uri:
        # response.status = 400
        # return {'errcode': 400, 'msg': 'Missing redirect_uri'}
        return redirect1("https://iam.gongshu.gov.cn/login/")
    if response_type != 'code':
        # response.status = 400
        # return {'errcode': 400, 'msg': 'Invalid response_type'}
        return redirect1("https://iam.gongshu.gov.cn/login/")
    # github_auth_url = f"{AUTHORIZATION_URL}?response_type={response_type}&state={state}&redirect_uri={redirect_url}&client_id={client_id}"
    return redirect1(github_auth_url)


@route('/auth3')
def callback():
    code = request.query.code
    state = request.query.state
    # redirect_uri_with_state = redirect_uri + f'?state={state}&code={code}'

    if not code:
        return redirect1(github_auth_url)
    # if state != session.get()
    # 交换授权码以获取访问令牌
    token_response = get_access_token(clientID, clientSecret, code, state)

    if token_response.status_code != 200:
        response.status = token_response.status_code
        return {'error': 'Failed to obtain token', 'response': token_response.text}

    token_response_data = token_response.json()

    access_token = token_response_data.get('access_token')

    if not access_token:
        return ujson.dumps({"success":False,"msg":"Token认证过期！"},ensure_ascii=False)
    try:
        # 使用访问令牌获取用户信息
        user_response = ruser(access_token, clientID)
    except Exception as e:
        return {"error": "GET", "msg": e.__str__()}
    user_data = user_response.json()
    key = "use:APP-DLP-SE"
    # 获取到用户id
    user_name = user_data.get("user_name")
    user_dic = {
        # "79777604":"任智超",
        "79776063": "邱礼开",
        "10527070": "柳锋"
    }
    if user_name and user_name in user_dic:
        user_name = user_dic.get(user_name) or user_name
        # is_superuser = user_name in SUPERUSER_WHITELIST
        session = get_session_id(user_name)

        list1 = [9008, 9009, 9010, 9011]
        eng = random.choice(list1)
        response.set_cookie("fbi_session", session, path="/")
        response.set_cookie("userName", session, path="/")
        response.set_cookie("eng", str(eng), path="/")
        response.set_cookie("work_space", path="/")
        fea_session_key = "fbi_session:%s" % (session)
        ssdb0.set(fea_session_key, "%s:%s" % (user_name, "Y"))
        return redirect1("https://59.202.68.91:8443/wap.h5?key=%s" % key)
    else:

        return ujson.dumps({"success":False,"msg":"您没有用户权限！"},ensure_ascii=False)


def get_access_token(client_id, client_secret, code, state):
    TOKEN_URL = 'https://iam.gongshu.gov.cn/bam-protocol-service/oauth2/getToken'
    params = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": 'authorization_code',
        "state": state
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    res = requests.post(TOKEN_URL, params=params, headers=headers)
    return res


def ruser(access_token, clientID):
    url = 'https://iam.gongshu.gov.cn/bam-protocol-service/oauth2/getUserInfo'
    headers = {

        "Cookie": f"JSESSIONID={access_token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    params = {
        "access_token": access_token,
        "client_id": clientID
    }
    res = requests.get(url=url, params=params, headers=headers)
    return res
