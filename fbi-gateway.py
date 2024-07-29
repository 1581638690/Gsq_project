#!/opt/fbi-base/bin/python
# -*- coding: utf-8 -*-


import importlib
from bottle import route, run, static_file, request, response, default_app, template, redirect, download_file

try:
    import ujson as json
except:
    import json
import sys

sys.path.append("lib")

from multiprocessing import Process, current_process
from urllib.parse import quote

import traceback
import os, signal, shutil

import time
import hashlib
from datetime import datetime
import copy
import urllib3
from urllib.parse import urlencode

import random
import base64
import zipfile
import glob
import pandas as pd

pd.options.future.infer_string = True
from avenger.sysrule import build_sysrule
from avenger.fbicommand import run_command2, run_block_in_sync
from avenger.fsys import *
from avenger.fssdb import *
from avenger.fastbi import compile_fbi
from avenger.fglobals import *
from avenger.fio import *
from avenger.fbiobject import FbiEngMgr

# add by gjw on 2022-1012 支持扩展的请求函数
try:
    from fbi_extends import *
except:
    pass

# add by gjw on 2022-0511 注册信号，装载脚本
import avenger.fsys

# 获取授权信息
c, s = rd_Authorization()
fbi_global.size = c
fbi_global.dbd_size = s

ssdb0 = fbi_global.get_ssdb0()
# 引擎管理
fbi_eng_mgr = FbiEngMgr(ssdb0)
# 用户管理
fbi_user_mgr = FbiUserMgr(ssdb0)

# 全局的session会话时间
timeout = get_key2("session_timeout") or "3600"
itimeout = int(timeout)

#
import logging
from logging.handlers import RotatingFileHandler

# 初始化主root
root_logger = logging.getLogger('fbi-gateway')
root_logger.setLevel(logging.INFO)
# 创建一个handler，用于写入日志文件
# 定义一个RotatingFileHandler，最多备份3个日志文件，每个日志文件最大1M
fh = RotatingFileHandler('logs/fbi_gateway.log', maxBytes=1024 * 1024, backupCount=0)

# 定义handler的输出格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
# 给logger添加handler
root_logger.addHandler(fh)
# 不向上传播到root
root_logger.propagate = 0

# add by gjw on 2021-0907 更好的记录udf中发生的错误
from avenger.fglobals import logger

# 给logger添加handler
logger.addHandler(fh)
# 不向上传播到root
logger.propagate = 1


# 免密登录
# 使用示例:http://ip/app?user=ddd&AK=27a9a7d16a8ab627cd6718d400a491864e4db3f4&key=use:zy
# 可以添加端口号：
# http://ip/app?user=ddd&AK=27a9a7d16a8ab627cd6718d400a491864e4db3f4&key=use:zy&port=8080
@route('/app', method="GET")
def app_mianmi():
    user = request.query.user
    ak = request.query.AK
    # 类型分为几种,可以是应用,可以是dashboad
    key = request.query.key
    # add by gjw on 2021-10-14,可以传递其他参数
    others = []
    for k, v in request.query.items():
        if k not in ["user", "AK", "key", "port"]:
            others.append("%s=%s" % (k, v))
    other_p = "&".join(others)
    PK = get_key("PK")
    xxx = user + key + fbi_user_mgr.get_passwd(user) + PK

    # 内部ak的hash
    def hash_str(x):
        h = hashlib.sha1()
        y = x[2:3] + x[1:4] + x[0:2] + x[5] + x
        h.update(y.encode("utf8"))
        return h.hexdigest()

    if ak == hash_str(xxx):
        session = get_session_id(user)
        list1 = [9008, 9009, 9010, 9011]
        eng = random.choice(list1)

        # add by gjw on 2023-1010
        if request.get_header("fbi_area"):
            response.set_cookie("fbi_session_{}".format(request.get_header("fbi_area")), session, path="/")
        else:
            response.set_cookie("fbi_session", session, path="/")

        response.set_cookie("userName", user, path="/")

        response.set_cookie("eng", str(eng), path="/")
        fea_session_key = "fbi_session:%s" % (session)
        user_info = fbi_user_mgr.get_user_by_name(user)
        ssdb0.set(fea_session_key, "%s:%s" % (user, user_info["isadmin"]))
        build_sysrule(ssdb0, user_info)
        if "port" not in request.query:
            path = "/wap.h5?key=%s&%s" % (key, other_p)
        else:
            path = ":%s/wap.h5?key=%s&%s" % (request.query.port, key, other_p)
        return redirect(path)
    else:
        return "AK  incorrect , access denied."


# 更改密码，要验证老密码
@route('/up_auth_key', method="POST")
def up_auth_key():
    ret = check_session(request, response)
    if ret != 0:
        return "{}"
    try:
        data = request.params.get("data")
        user = json.loads(data)

        # 校验老密码
        if "old_auth_key" not in user:
            raise Exception("不能修改密码，请升级UI版本到2022-0324之后!")
        old_pwd = user["old_auth_key"]
        old_pwd = base64.b64decode(old_pwd).decode("utf8")

        pwd = user["auth_key"]
        pwd = base64.b64decode(pwd).decode("utf8")
        if len(pwd) < 8: raise Exception("新密码不能少于8位!")
        session = get_session(request)

        if user["name"] == get_user_by_session(session)[0]:
            auth_code = fbi_user_mgr.auth2_user(user["name"], old_pwd, request.remote_addr)  # 任意用户都可以修改
            if auth_code == 1:
                fbi_user_mgr.update_passwd(user["name"], pwd)
                return json.dumps({"success": True})
            else:
                raise Exception("旧密码验证失败，无法更新密码!")
        else:
            raise Exception("非当前用户无法更新密码!")
    except Exception as e:
        return '{"success":false,"err":"%s"}' % (e)


@route('/put/<db>/<key>', method="POST")
def ssdb_put(db, key):
    try:
        value = request.params.get("value")
        ret = check_session(request, response)
        if ret != 0:
            raise Exception("没有认证!")

        if key.find("=>") > 0:
            name, subkey = key.split("=>")
            ssdb0.hset(b64(name), b64(subkey), value)
        else:
            # add by gjw on 2020-1222, 配置数据只有开发权限才能保存
            if check_ssdb_key_is_write(key):
                check_isadmin(request)
            ssdb0.set(b64(key), value)
        return '{"success":1}'
    except Exception as e:
        return '{"success":false,"err":"%s"}' % (e)


@route('/format')
def fbi_format():
    # 格式化FbI
    ret = check_session(request, response)
    if ret != 0:
        return "{}"
    session = get_session(request)
    fbi_name = request.query.name
    fbi_name = fbi_name.replace("--", "/")
    format_script(file_path["fbi"] + fbi_name, get_user_by_session(session)[0])
    return '{"success":1}'


@route('/list')
def list_alltable():
    ret = check_session(request, response)
    if ret != 0:
        return "{}"
    return json.dumps(list(fbi_global.get_runtime().wss.keys()))


# add by gjw on 20200829, 保存智能事件分析器的配置
@route('/ev/<key>', method="POST")
def events(key):
    ret = check_session(request, response)
    if ret != 0:
        return '{"success":0,"err":"验证失败!"}'
    try:
        # 完整json body 的获取方式
        cfg = request.json
        ssdb0.set(b64("#event:" + key), json.dumps(cfg))
        # 解析生成ev的脚本内容
        from avenger.events import parse_cfg
        script, script_debug, ps, timer_meta = parse_cfg(cfg, key)
        ssdb0.set(b64("#event_script:" + key), script)
        ssdb0.set(b64("#event_prmtv:" + key), json.dumps(ps))
        ssdb0.set(b64("#timer_meta:event" + key), json.dumps(timer_meta))
        try:
            with open("/opt/openfbi/fbi-bin/script/ev/model%s.fbi" % (key), "w+") as f:
                f.write(script)
            with open("/opt/openfbi/fbi-bin/script/ev/model%s_debug.fbi" % (key), "w+") as f:
                f.write(script_debug)
            compile_fbi("ev/model%s.fbi" % (key))
            compile_fbi("ev/model%s_debug.fbi" % (key))
        # send_reload_signal_to_all("ev/model%s.fbi"%(key))
        # send_reload_signal_to_all("ev/model%s_debug.fbi"%(key))
        except:
            pass
        return '{"success":1}'
    except Exception as e:
        return '{"success":0,"err":"%s"}' % (e)


# add by gjw on 20211015, 智能事件分析器的管理
@route('/evm/<key>')
def events_manager(key):
    ret = check_session(request, response)
    if ret != 0:
        return '{"success":0,"err":"验证失败!"}'
    result = {"success": 1}
    port = request.params.eng or request.cookies.eng or "9002"
    session = get_session(request)
    user = get_user_by_session(session)[0]
    try:
        action = request.query.action
        if action == "prmtv":
            ps = ssdb0.get("#event_prmtv:" + key)
            ret = json.loads(ps)
        elif action == "start":
            ret = evs_start_task(key, port, user)
        elif action == "debug":
            ret = evs_start_task(key, port, user, True)
        else:  # update
            pass
        result["ret"] = ret
    except Exception as e:
        result["success"] = 0
        result["err"] = e.__str__()

    return json.dumps(result)


##启动任务
def evs_start_task(key, port, user, debug=False):
    # add by gjw on 20200907 事件引擎的调度
    if debug:
        a = [key, "", "ev/model%s_debug.fbi" % (key)]
    else:
        a = [key, "", "ev/model%s.fbi" % (key)]
    timer_meta = ssdb0.get("#timer_meta:event%s" % (a[0]))

    if timer_meta != None and timer_meta != "":
        meta = json.loads(timer_meta)
        now = datetime.now()
        meta["endT"] = now.isoformat()
        from datetime import timedelta
        if meta["type"] == "滑动窗口":
            meta["beginT"] = (now - timedelta(minutes=meta["roll_size"])).isoformat()
        else:
            meta["beginT"] = (now - timedelta(minutes=meta["timer"])).isoformat()

        # 准备运行
        prmtv = "run " + a[
            2] + " with @model={model}, @version={version},@timestamp={@timestamp},@beginT={beginT},@endT={endT}".format(
            **meta)
        d = local_run("127.0.0.1", port, prmtv, "", user)

        # 运行结果
        if d["ret"] == 1:
            meta["error"] = "[%s][%s]手工调度失败:[%s] %s" % (
                now.isoformat(), a[0], datetime.now().isoformat(), d["error"])

        ssdb0.set("#timer_meta:%sevent" % (a[0]), json.dumps(meta))
        return d
    # end if
    return {"error": "没有找到相应的配置信息!"}


# end  evs_start_task


# add by gjw on 20200709, 完整json body 的获取方式
@route('/lg/<key>', method="POST")
def logstash(key):
    ret = check_session(request, response)
    if ret != 0:
        return '{"success":0,"err":"验证失败!"}'
    try:
        cfg = request.json
        ssdb0.set(b64("#logs:" + key), json.dumps(cfg))
        # 解析生成logstash配置文件
        from avenger.logstash import parse_cfg
        scfg = parse_cfg(cfg)
        ssdb0.set(b64("#logstash:" + key), scfg)
        try:
            with open("/opt/lg/pipeline/%s.conf" % (key), "w+") as f:
                f.write(scfg)
        except:
            pass
        return '{"success":1}'
    except Exception as e:
        return '{"success":0,"err":"%s"}' % (e)


# add by gjw on 20200712, 控制实例的启停
@route('/lgs/<key>')
def logstash(key):
    ret = check_session(request, response)
    if ret != 0:
        return '{"success":0,"err":"验证失败!"}'
    from avenger.logstash import lg_start, lg_stop, lg_update
    try:
        action = request.query.action
        if action == "start":
            ret = lg_start(key)
        elif action == "stop":
            ret = lg_stop(key)
        else:  # update
            ret = lg_update(key)
        return '{"success":1,"ret":"%s"}' % (ret)
    except Exception as e:
        return '{"success":0,"err":"%s"}' % (e)


# add by gjw on 20200722, 实例的监控
@route('/lgm/<key>')
def logstash_moniter(key):
    ret = check_session(request, response)
    if ret != 0:
        return '{"success":0,"err":"验证失败!"}'
    from avenger.logstash import lg_m_pipeline, lg_m_cfg
    result = {"success": 1}
    try:
        action = request.query.action
        if action == "cfg":
            ret = lg_m_cfg(key)
        elif action == "pipeline":
            ret = lg_m_pipeline(key)
        else:  # update
            ret = lg_m_pipeline(key)
        result["ret"] = ret
    except Exception as e:
        result["success"] = 0
        result["err"] = e.__str__()

    return json.dumps(result)


# 日志跟踪
@route('/putlog', method="POST")
def put_log():
    try:
        value = request.params.get("value")
        session = get_session(request)

        user = get_user_by_session(session)[0]
        if user == None or user == "":  return "you can't access data!"
        # 日志详情
        putlog_ssdb(user, value, request.remote_addr)
        response.set_header("Content-Type", 'application/json; charset=UTF-8')
        return '{"success":1}'
    except:
        return '{"success":false,"err":"未知的格式"}'


def putlog_ssdb(user, value, remote_addr, operate_result=None, failed_reason=None):
    d = json.loads(value)
    d["user"] = user
    d["remote_addr"] = remote_addr
    d["remote_route"] = remote_addr
    d["timestamp"] = datetime.now().isoformat()
    if operate_result:
        d["operate_result"] = operate_result
    if failed_reason:
        d["failed_reason"] = failed_reason
    ssdb0.qpush("Q_log_%s" % (d["timestamp"][0:10]), json.dumps(d))


# 临时key数据
@route('/put300/<db>/<key>', method="POST")
def ssdb_put300(db, key):
    try:
        ret = check_session(request, response)
        if ret != 0:
            return ret

        value = request.params.get("value")
        ssdb0.set(b64(key), value)
        ssdb0.expire(b64(key), 300)
        return '{"success":1}'
    except Exception as e:
        return '{"success":false,"err":"%s"}' % (e)


# 发送消息
@route('/send_mq', method="POST")
def send_mq():
    try:
        ret = check_session(request, response)
        if ret != 0:
            return "{'success':0,'err':'没有认证，无法发送消息！'}"
        import redis
        mq = request.params.get("mq")
        link = request.params.get("msg")
        # 验证msg的内容是不是标准json
        link_json = json.loads(link)
        r = redis.Redis(config["redis_host"], port=config["redis_port"], decode_responses=True,
                        password=config["redis_password"])
        r.publish(mq, json.dumps(link_json))
        return '{"success":1}'
    except Exception as e:
        return '{"success":0,"err":"%s"}' % (e)


# 检查redis是否正常
@route('/check_redis', method="GET")
def check_redis():
    try:
        ret = check_session(request, response)
        if ret != 0:
            return "{'success':0,'err':'没有认证，无法发送消息！'}"

        import redis
        r = redis.Redis(config["redis_host"], port=config["redis_port"], decode_responses=True,
                        password=config["redis_password"])
        r.ping()
        return '{"success":1}'
    except Exception as e:
        return '{"success":false,"err":"%s"}' % (e)


# 校验会话是否合法
def check_session(request, response):
    session = get_session(request)
    if session == "": return "you can't access data!"
    fbi_session = "fbi_session:%s" % (session)
    if ssdb0.exists(fbi_session) == "0": return "you can't access data!"
    return 0


# 返回fbi_session
def get_session(request):
    if request.get_header("fbi_area"):
        return request.get_cookie("fbi_session_{}".format(request.get_header("fbi_area")))

    session = request.query.fbi_session or request.params.fbi_session or request.cookies.fbi_session
    return session


# modify by gjw on 2020
# 返回用户名和用户是否具有开发权限
def get_user_by_session(session):
    fbi_session = "fbi_session:%s" % (session)
    v = ssdb0.get(fbi_session)
    if v != None and v != "":
        user, isadmin = v.split(":")
    else:
        raise Exception("you can't access data!")
    return user, isadmin


# add by gjw on 20201215 检查有无开发人员的权限
def check_isadmin(request):
    session = get_session(request)
    if not session:
        raise Exception("you can't access data!")
    user, isadmin = get_user_by_session(session)
    if (isadmin != "Y"):
        raise Exception("{}没有权限，不能操作!".format(user))
    return user


# 删除key
@route('/del/<db>/<key>')
def ssdb_del(db, key):
    try:
        check_isadmin(request)
        ssdb0.delete(b64(key))
        return '{"success":1}'
    except Exception as e:
        return '{"success":false,"err":"%s"}' % (e)


# add by gjw on 2020-1223
# 返回fbi状态
@route('/fbi_stats')
def query_fbi_stats():
    ret = check_session(request, response)
    if ret != 0:
        return ret
    try:
        with open('/dev/shm/fbi_stats', 'r') as f:
            a = f.read()
    except:
        a = "{}"
    return a


# 会话保活接口
@route('/KA')
def KA():
    try:
        session = get_session(request)
        if session == "": return "you can't access data!"
        # add by gjw on 2023-1207 是否强制超时判断force_session_timeout
        force_session_timeout = get_key("force_session_timeout")

        if force_session_timeout == "true":
            return json.dumps({"success": True, "fbi_session": session})
        # 进入保活流程
        fbi_session = "fbi_session:%s" % (session)
        user, isadmin = get_user_by_session(session)
        if user == None or user == "": return "you can't access data!"

        # 新session
        session = get_session_id(user)
        key = "fbi_session:%s" % (session)

        # add by gjw on 2022-0516 记录用户最后的会话
        last_Key = "{}:last_fbisession".format(user)

        # 删除改为５秒后超时
        # ssdb0.delete(fbi_session)
        ssdb0.expire(fbi_session, 5)

        ssdb0.set(key, user + ":" + isadmin)  # 当前session
        ssdb0.set(last_Key, session)
        ssdb0.expire(key, itimeout)

        if request.get_header("fbi_area"):
            response.set_cookie("fbi_session_{}".format(request.get_header("fbi_area")), session, max_age=itimeout,
                                path="/")
        else:
            response.set_cookie("fbi_session", session, max_age=itimeout, path="/")
        return json.dumps({"success": True, "fbi_session": session})
    except Exception as e:
        return '{"success":false,"err":"%s","traceback":"%s"}' % (e, traceback.format_exc())


# 门户应用的登出
@route('/logout')
def logout2():
    try:
        session = get_session(request)
        fbi_session = "fbi_session:%s" % (session)
        user_name = get_user_by_session(session)[0]
        if user_name == None or user_name == "": return "you can't access data!"
        ssdb0.delete(fbi_session)
        response.delete_cookie("fbi_session", path="/")
        log_session(user_name, request.remote_addr, ";".join(request.remote_route), "注销", "应用", \
                    "user:%s" % (user_name), "成功", "")
        return '{"success":1}'
    except Exception as e:
        response.delete_cookie("fbi_session")
        return '{"success":false,"err":"%s"}' % (e)


# 当前时间
@route('/now')
def system_now():
    now = datetime.now().isoformat()[0:19]
    curtime = {"now": now, "timestamp": int(time.time() * 1000)}
    return json.dumps(curtime)


# add by gjw on 20210421
# 开发平台的注销
@route('/logout2')
def logout():
    try:
        session = get_session(request)
        fbi_session = "fbi_session:%s" % (session)
        user_name = get_user_by_session(session)[0]
        if user_name == None or user_name == "": return "you can't access data!"
        ssdb0.delete(fbi_session)

        # 开发用户不允许在多个终端登录同一平台
        """
        #add by gjw on 2022-0213　可以有多个相同用户同时登录后台
        user_session_key = "user_session:{}:".format(user_name)
        #删除所有正在登录的用户的session
        user_sessions = ssdb0.keys(user_session_key,user_session_key+"~",1000)
        for user_session in user_sessions:
            user,name,session= user_session.split(":")
            ssdb0.delete( user_session)
            ssdb0.delete( "fbi_session:{}".format(session))
        """

        response.delete_cookie("fbi_session", path="/")
        log_session(user_name, request.remote_addr, ";".join(request.remote_route), "注销", "平台", \
                    "user:%s" % (user_name), "成功", "")
        return '{"success":1}'
    except Exception as e:
        response.delete_cookie("fbi_session")
        return '{"success":false,"err":"%s"}' % (e)


# 检查key是否为配置数据的key
def check_ssdb_key_is_cfg(key):
    k = key.split(":")
    if k[0] in ["word", "qes", "am", "modeling"] or k[0][0:-1] == "dashboard":
        return True
    return False


# 写权限的
def check_ssdb_key_is_write(key):
    k = key.split(":")
    if k[0] in ["word", "qes", "am", "modeling", "sys_data", "nav", "use", "sys_data", "qes_table"] or k[0][
                                                                                                       0:-1] == "dashboard":
        return True
    if k[0] in ["fbi_session", "SysRule"]:  # 系统级的数据，不允许管理员写入
        raise Exception("没有写权限!")
    return False


# add by gjw on 2020-1222,检查是否有获取面板类配置数据的权限,True为失败
def check_sysrule_dbds_failed(session, key_string):
    try:
        user, isadmin = get_user_by_session(session)
        if user == None or user == "": return True
        if isadmin == "Y": return False
        if user == "admin": return False

        SysRule = ssdb0.get("SysRule:dbds:%s" % (user))
        SysRule_list = json.loads(SysRule)

        keys = key_string.split(",")
        for key in keys:
            if check_ssdb_key_is_cfg(key):
                if key not in SysRule_list:
                    return True
        # False 为成功
        return False
    except:
        return False


# 获取数据key
@route('/query/<db>/<key:raw>')
def ssdb_query_json_one(db, key):
    response.set_header("Content-Type", 'application/json; charset=UTF-8')
    session = get_session(request)
    if session == "": return "you can't access data!"
    if check_sysrule_dbds_failed(session, key): return "you can't access data!"

    if key.startswith("printf::"):
        try:
            with open(f"/dev/shm/{key}", "r") as f:
                ret = f.read()
        except:
            ret = None
    else:
        ret = ssdb0.get(b64(key))
    if ret == None: ret = {}
    return "%s" % (ret)


# 获取数据key
@route('/query/<db>', method=['POST', 'GET'])
def ssdb_query_json(db):
    response.set_header("Content-Type", 'application/json; charset=UTF-8')
    # key = request.query.key
    key = request.params.get("key")
    session = get_session(request)
    if session == "": return "you can't access data!"
    if check_sysrule_dbds_failed(session, key): return "you can't access data!"

    def get_hashitem(key):
        name, subkey = key.split('=>')
        if key.endswith('=>*'):
            hvalue = ssdb0.hgetall(b64(name))
            name_key = [b64(name) + "=>" + k for k in hvalue[::2]]
            r_key = [name + "=>" + db64(k) for k in hvalue[::2]]
            subvalue = hvalue[1::2]
            newvalue = []
            for value in subvalue:
                if value == None:
                    value1 = {}
                else:
                    try:
                        value1 = json.loads(value)
                    except ValueError as e:
                        value1 = value
                newvalue.append(value1)
            return dict(zip(r_key, newvalue))
        else:
            subvalue = ssdb0.hget(b64(name), b64(subkey))
            if subvalue == None:
                subvalue1 = {}
            else:
                try:
                    subvalue1 = json.loads(subvalue)
                except ValueError as e:
                    subvalue1 = subvalue
            return {key: subvalue1}

    def get_item(key):
        value = ssdb0.get(b64(key))
        if value == None: value = "{}"
        return value

    if key.find("=>") == -1:  # 正常key
        if key.find(",") == -1:
            # 单个key处理
            return get_item(key)
        else:
            result = []
            keys = key.split(',')
            for key in keys:
                result.append(f'"{key}":{get_item(key)}')
            return "{%s}" % (",".join(result))
    else:  # hash的查找
        return json.dumps(get_hashitem(key))


import pandas as pd


# 执行udf函数
@route('/udf/<pkg_fun>', method=['POST', 'GET'])
def udf_fun(pkg_fun):
    from avenger.fbiprocesser import _dump_df
    response.set_header("Content-Type", 'application/json; charset=UTF-8')
    df_json = request.params.get("df")
    p = request.params.get("p")
    pkg, fun = pkg_fun.split(".")
    session = get_session(request)
    if session == "": return "you can't access data!"
    result = {"status": 0, "dfs": {}}
    try:
        if df_json == None or df_json == "":
            df = pd.DataFrame()
        else:
            df = pd.read_json(df_json)

        # exec("from udf.%s import %s "%(pkg,fun))
        # dfs = eval("%s(df,p)"%(fun))

        udf = importlib.import_module("udf.%s" % (pkg))
        dfs = getattr(udf, fun)(df, p)

        if isinstance(dfs, pd.DataFrame):
            result["dfs"][0] = _dump_df(dfs)
        else:
            for i, dfz in enumerate(dfs):
                result["dfs"][i] = _dump_df(dfz)
    except Exception as e:
        result["status"] = 1
        result["errors"] = e.__str__()
    finally:
        if "udf.%s" % (pkg) in sys.modules:
            del (sys.modules["udf.%s" % (pkg)])
    return json.dumps(result)


# 检查是否存在XSS攻击
def check_xss(callback):
    keys = ["<", ">", "'", '"', "%", "*", "$"]
    for i in keys:
        if i in callback:
            raise Exception("可能存在XSS攻击，不执行后续请求!")


# 扫描多个key
@route('/scan/<db>/<skey>/<ekey>')
def ssdb_scan_json(db, skey, ekey, count=100):
    try:
        user = check_isadmin(request)
    except Exception as e:
        return e.__str__()
    response.set_header("Content-Type", 'application/json; charset=UTF-8')

    a = ssdb0.scan(skey, ekey, fbi_global.dbd_size)
    length = len(a)
    b = []
    for i in range(0, length, 2):
        d = {}
        d[a[i]] = a[i + 1]
        b.append(d)
    ret = json.dumps(b)
    return ret


# 全文检索面板内容
@route('/full/<db>/<skey>/<ekey>/<text>')
def ssdb_full_dbd(db, skey, ekey, text):
    try:
        user = check_isadmin(request)
    except Exception as e:
        return e.__str__()
    response.set_header("Content-Type", 'application/json; charset=UTF-8')
    a = ssdb0.scan(skey, ekey, 10000)
    length = len(a)
    b = []
    for i in range(0, length, 2):
        if a[i].find(text) >= 0 or a[i + 1].find(text) >= 0:  # key和value都找
            d = {}
            d[a[i]] = a[i + 1]
            b.append(d)
    # end for
    ret = json.dumps(b)
    return ret


# 获取字典
@route('/scan/dd')
def ssdb_scan_dd():
    response.set_header("Content-Type", 'application/json; charset=UTF-8')
    ret = check_session(request, response)
    if ret != 0:
        return ret
    a = ssdb0.keys("dd:", "dd:~", 10000)
    ret = json.dumps(a)
    return ret


# 面板数量的统计
@route('/dbd_sum')
def dbd_sum():
    response.set_header("Content-Type", 'application/json; charset=UTF-8')
    ret = check_session(request, response)
    if ret != 0:
        return ret
    dbd_sums = {}
    for dbd in ["dashboard3", "dashboard7", "am", "modeling", "qes", "word", "nav", "use"]:
        a = ssdb0.keys(dbd + ":", dbd + ":~", 10000)
        dbd_sums[dbd] = len(a)
    return json.dumps(dbd_sums)


# 获取字典的描述信息
@route('/scan/dd2')
def ssdb_scan_dd2():
    response.set_header("Content-Type", 'application/json; charset=UTF-8')
    ret = check_session(request, response)
    if ret != 0:
        return ret
    a = ssdb0.scan("dd2:", "dd2:~", 10000)
    length = len(a)
    b = []
    dd2_key = []
    for i in range(0, length, 2):
        d = {}
        d[a[i]] = a[i + 1]
        b.append(d)
        dd2_key.append(a[i])
    dd2_key = map(lambda x: x[4:], dd2_key)
    a = ssdb0.keys("dd:", "dd:~", 10000)
    dd_key = map(lambda x: x[3:], a)
    dd = list(set(dd_key) - set(dd2_key))
    dd2 = map(lambda x: "dd2:" + x, dd)
    for k in dd2:
        d = {k: '{"id":"%s"}' % (k[4:])}
        b.append(d)
    ret = json.dumps(b)
    return ret


# 获取define的值
@route('/define/<key>')
def get_define(key):
    ret = check_session(request, response)
    if ret != 0:
        return ret
    value = get_key(key)
    return value


PK = ""


# 获取PK码
@route('/PK')
def get_PK():
    ret = check_session(request, response)
    if ret != 0:
        return ret
    global PK
    if PK == "":
        PK = get_key("PK")
    return PK


# 所有用户信息
@route('/list_user')
def list_user():
    try:
        user = check_isadmin(request)
    except Exception as e:
        return e.__str__()
    res = fbi_user_mgr.get_all_user(user)
    return json.dumps(res)


# 单个用户信息
@route('/get_user/<name>')
def list_user_by_name(name):
    ret = check_session(request, response)
    if ret != 0:
        return ret
    res = fbi_user_mgr.get_user_by_name(name)
    return json.dumps(res)


# auth认证的实体函数,登录开发平台
@route('/auth', method="POST")
def auth():
    try:
        failed_session = get_key2("failed_session") or "60"
        # 登陆失败重试次数
        retry_count = get_key2("retry_count") or "3"
        fail_key = "FAIL:%s" % (request.remote_addr)
        fail_cnt = ssdb0.get(fail_key)

        try:
            retry_count = int(retry_count)
        except:
            retry_count = 3
        data = request.params.get("data")
        user = json.loads(data)

        pwd = user["auth_key"]
        pwd = base64.b64decode(pwd).decode("utf8")
        pwd = pwd.strip()
        if fail_cnt != None and int(fail_cnt) >= retry_count:
            log_session(user["name"], request.remote_addr, ";".join(request.remote_route), "登录", "平台", \
                        "user:%s " % (user["name"]), "失败", "连续[%s]次登录失败,请过会再试!" % (retry_count))
            raise Exception("连续登录失败,请过会再试!")

        if len(pwd) < 8:
            log_session(user["name"], request.remote_addr, ";".join(request.remote_route), "登录", "平台", \
                        "user:%s,auth_key:%s" % (user["name"], pwd), "失败", "验证失败，密码小于8位!")
            raise Exception("验证失败，请确认用户名和密码有效再登录!")
        auth_code = fbi_user_mgr.auth_user(user["name"], pwd, request.remote_addr)

        if auth_code == 1:
            # 设置cookie
            # 返回portal和nav
            ret = fbi_user_mgr.get_user_by_name(user["name"])
            # 获取session
            session = get_session_id(user["name"])
            key = "fbi_session:%s" % (session)

            """
            #add by gjw on 2022-0213　可以有多个相同用户同时登录后台
            user_sessions = "user_session:{}:{}".format(user["name"],session)
            ssdb0.set(user_sessions, session)
            ssdb0.expire(user_sessions, itimeout)
            """

            # add by gjw on 2024-0108 记录用户最后的会话
            last_Key = "{}:last_fbisession".format(user["name"])
            last_session = ssdb0.get(last_Key)
            if last_session != None and last_session != "":
                ssdb0.delete("fbi_session:%s" % (last_session))
            ssdb0.set(last_Key, session)

            # 记录本次session
            ssdb0.set(key, user["name"] + ":" + ret["isadmin"])
            ssdb0.expire(key, itimeout)

            # add by gjw on 2022-0519 返回eng
            eng = fbi_eng_mgr.get_user_eng(user["name"])

            # 固化到前端
            response.set_cookie("fbi_session", session, max_age=itimeout, path="/")
            response.set_cookie("eng", eng, max_age=itimeout, path="/")
            response.set_cookie("work_space", "public", max_age=itimeout, path="/")

            log_session(user["name"], request.remote_addr, ";".join(request.remote_route), "登录", "平台", \
                        "user:%s" % (user["name"]), "成功", "")
            return json.dumps({"success": True, "fbi_session": session})
        elif auth_code == 0:
            log_session(user["name"], request.remote_addr, ";".join(request.remote_route), "登录", "平台",
                        "user:%s,auth_key:%s" % (user["name"], pwd), "失败", "验证失败，请确认用户名和密码有效再登录!")
            raise Exception("验证失败，请确认用户名和密码有效再登录!")
        else:
            log_session(user["name"], request.remote_addr, ";".join(request.remote_route), "登录", "平台",
                        "user:%s " % (user["name"]), "失败", "验证失败，您的ip不允许登陆该账户!")
            raise Exception("验证失败，您的ip不允许登陆该账户!")
    except Exception as e:
        # root_logger.error(traceback.format_exc())
        try:
            # add by gjw on 20180302
            if ssdb0.exists(fail_key) == "0":  # 不存在
                ssdb0.set(fail_key, 1)
                ssdb0.expire(fail_key, 50)
            else:
                ssdb0.incr(fail_key, 1)  # 存在加1
                ssdb0.expire(fail_key, 50)
        except Exception as e2:
            return '{"success":false,"err":"认证出错:%s-%s"}' % (e, e2)
        return '{"success":false,"failed_session":"%s","err":"%s"}' % (failed_session, e)


# add by gjw on 20200201, 集群添加节点
@route('/addnode', method="POST")
def addnode():
    d = {"ret": -1}
    datas = request.params.get("data")
    data = New_decrypt(CK, datas)
    host, user, passwd = data.split(",")
    auth_code = fbi_user_mgr.auth_user(user.strip(), passwd.strip(), request.remote_addr)
    if auth_code == 1:
        d["ret"] = 0
        # 生成之后run的秘钥 sha1(data+当前日期)
        AK = my_hash(data)
        name = request.params.get("name")
        add_master(name, request.remote_addr, AK, user)
        d["AK"] = New_encrypt(CK, AK)
        d["msg"] = "添加节点成功!"
        loglog(user, request.remote_addr, ";".join(request.remote_route), "集群认证", "后台系统", \
               "添加节点成功!user:%s" % (user), "成功", "")
    elif auth_code == 0:
        d["msg"] = "验证失败，请确认用户名和密码有效再添加!"
        loglog(user, request.remote_addr, ";".join(request.remote_route), "集群认证", "后台系统", \
               "user:%s,auth_key:%s" % (user, passwd), "失败", d["msg"])
    else:
        d["msg"] = "验证失败，您的ip不允许登陆该账户!"
        loglog(user, request.remote_addr, ";".join(request.remote_route), "集群认证", "后台系统", \
               "user:%s,auth_key:%s" % (user, passwd), "失败", d["msg"])
    return json.dumps(d)


# add by gjw on 20200201, 集权节点运行远程任务,结果信息在是完整加密的json内容，确保对方的身份
@route('/node', method="POST")
def node_run():
    d = {"ret": -1}
    datas = request.params.get("data")
    node = request.params.get("name")
    eng = request.params.get("eng")
    block = request.params.get("blocks")
    node_info = get_master_by_name(node)
    if node_info == None:
        d["msg"] = "[%s]节点信息在远程找不到!" % (node)
        return New_encrypt(node_info[1], json.dumps(d))
    if node_info[0] != request.remote_addr:
        d["msg"] = "[%s]master主机信息不匹配!" % (request.remote_addr)
        return New_encrypt(node_info[1], json.dumps(d))
    try:
        data = New_decrypt(node_info[1], datas)
    except:
        d["msg"] = "不能识别的通信回话!"
        return New_encrypt(node_info[1], json.dumps(d))
    # 运行
    if eng == "0":  # 同步执行
        d = local_runp("127.0.0.1", eng, data, "public", node_info[2])
    elif block == "block":
        d = local_run_block("127.0.0.1", eng, data, "public", node_info[2])
    elif eng == "9000":  # 采用本地定时调度引擎执行， 2022-0318

        put_timer("{}_{}".format(node, time.time()), "* * * * * *", data)
        d["ret"] = 0
        d["error"] = ""
        d["result"] = []
    else:  # 异步执行
        d = local_run("127.0.0.1", eng, data, "public", node_info[2])

    if "result" in d and isinstance(d["result"], list) and len(d["result"]) > 0:
        d["result"][0]["TI"] = "%s:%s" % (d["result"][0]["TI"], node)
    return New_encrypt(node_info[1], json.dumps(d))


# add by gjw on 20211224, 集权节点ssdb交互
@route('/ssdb_rw', method="POST")
def ssdb_rw():
    from avenger.fio import load_data_by_ssdb, store_to_ssdb
    d = {"ret": -1}
    datas = request.params.get("ptree")
    node = request.params.get("name")

    node_info = get_master_by_name(node)
    if node_info == None:
        d["msg"] = "[%s]节点信息在远程找不到!" % (node)
        return New_encrypt(node_info[1], json.dumps(d))
    if node_info[0] != request.remote_addr:
        d["msg"] = "[%s]master主机信息不匹配!" % (request.remote_addr)
        return New_encrypt(node_info[1], json.dumps(d))
    try:
        data = New_decrypt(node_info[1], datas)
    except:
        d["msg"] = "不能识别的通信回话!"
        return New_encrypt(node_info[1], json.dumps(d))
    # 正式业务处理
    try:
        d["ret"] = 0
        ptree = json.loads(data)
        key = b64(ptree["with"])
        if ptree["Action"] == "load":
            value = ssdb0.get(key)
            if value != None:
                d["data"] = value
        elif ptree["Action"] == "store":
            ssdb0.set(key, ptree["data"])
            if "as" in ptree:
                ssdb0.expire(key, int(ptree["as"]))
        else:
            d["msg"] = "不能识别的原语!"
    except:
        d["ret"] = -1
        d["msg"] = "原语执行出错"

    return New_encrypt(node_info[1], json.dumps(d))


# 使用队列记录操作日志
def loglog(user, ip, route, action, nav, params, result, reason):
    d = {}
    d["user"] = user
    d["remote_addr"] = ip
    d["remote_route"] = route,
    d["timestamp"] = datetime.now().isoformat()
    d["action"] = action
    d["nav_name"] = nav
    d["params"] = params
    d["operate_result"] = result
    d["failed_reason"] = reason
    ssdb0.qpush("Q_log_%s" % (d["timestamp"][0:10]), json.dumps(d))


# 使用队列记录回话日志（登录和登出）
# add 登录登出会同时记录到操作日志中
def log_session(user, ip, route, action, nav, params, result, reason):
    d = {}
    d["user"] = user
    d["remote_addr"] = ip
    d["remote_route"] = route,
    d["timestamp"] = datetime.now().isoformat()
    d["action"] = action
    d["nav_name"] = nav
    d["params"] = params
    d["operate_result"] = result
    d["failed_reason"] = reason
    ssdb0.qpush("Q_log2_%s" % (d["timestamp"][0:10]), json.dumps(d))
    ssdb0.qpush("Q_log_%s" % (d["timestamp"][0:10]), json.dumps(d))


# add by gjw on 20200319,获取登录token
@route('/login_token')
def get_token():
    token = random.randint(0, 1000)
    key = "token:%s:%s" % (request.remote_addr, token)
    ssdb0.set(key, "Y")
    ssdb0.expire(key, 1800)
    return '{"token":%s}' % (token)


# auth2认证的实体函数
# 门户的验证
@route('/auth2', method="POST")
def auth2():
    try:
        # modify by gjw on 2021-0315 登录失败锁定时间
        lock_times = get_key2("failed_session") or "60"
        try:
            lock_times = int(lock_times)
        except:
            lock_times = 60

        # 登陆失败重试次数
        retry_count = get_key2("retry_count") or "3"
        try:
            retry_count = int(retry_count)
        except:
            retry_count = 3

        fail_key = "FAIL:%s" % (request.remote_addr)
        fail_cnt = ssdb0.get(fail_key)

        data = request.params.get("data")
        user = json.loads(data)

        # 密码有效时间天数
        long_time = get_key2("long_time") or "0"
        try:
            long_time = int(long_time)
        except:
            long_time = 0

        pwd = user["auth_key"]
        pwd = base64.b64decode(pwd).decode("utf8")
        pwd = pwd.strip()
        if fail_cnt != None and int(fail_cnt) >= retry_count:
            log_session(user["name"], request.remote_addr, ";".join(request.remote_route), "登录", "应用", \
                        "user:%s " % (user["name"]), "失败", "连续[%s]次登录失败,请过会再试!" % (retry_count))
            raise Exception("连续登录失败,请过会再试!")

        if len(pwd) < 6:
            log_session(user["name"], request.remote_addr, ";".join(request.remote_route), "登录", "应用", \
                        "user:%s,auth_key:%s" % (user["name"], pwd), "失败", "验证失败，密码小于6位!")
            raise Exception("验证失败，请确认用户名和密码有效再登录!")

        auth2_code = fbi_user_mgr.auth2_user(user["name"], pwd, request.remote_addr)
        if auth2_code == 1:
            # 返回portal和nav,其实是port和app
            ret = fbi_user_mgr.get_user_by_name(user["name"])
            loginday = False
            if long_time != 0:
                # 账户修改的时间
                if "modificationdate" in ret:
                    timestamp_ = ret["modificationdate"]
                else:
                    timestamp_ = 0
                # 当前时间
                current_time = time.time()
                # 天差
                diff_days = (current_time - timestamp_) / (24 * 60 * 60)
                # print(diff_days)
                if diff_days > long_time:
                    loginday = True
            # max_age=itimeout,
            if ret["nav"] == "":
                raise Exception("没有指定的应用，无法登录!")

            # 获取session
            session = get_session_id(user["name"])
            key = "fbi_session:%s" % (session)

            # add by gjw on 2022-0516 记录用户最后的会话
            # last_Key = "{}:last_fbisession".format(user["name"])
            # last_session = ssdb0.get(last_Key)
            # if last_session !=None and last_session !="":
            # 	ssdb0.delete("fbi_session:%s" % (last_session))
            # ssdb0.set(last_Key, session)

            ssdb0.set(key, user["name"] + ":" + ret["isadmin"])
            ssdb0.expire(key, itimeout)

            # add by gjw on 2020-1222 增加系统规则的生成函数
            try:
                build_sysrule(ssdb0, ret)
            except:
                pass

            # add by gjw on 2022-0519
            eng = ""
            if ret["isadmin"] == "Y":
                eng = fbi_eng_mgr.get_user_eng(user["name"])

            # 是否初始化密码
            initial = False
            if pwd == "ABC@2020":
                initial = True

            # add by gjw on 2023-01010 fbi的area
            if request.get_header("fbi_area"):
                response.set_cookie("fbi_session_{}".format(request.get_header("fbi_area")), session, path="/")
            else:
                response.set_cookie("fbi_session", session, path="/")
            response.set_cookie("eng", eng, path="/")
            response.set_cookie("work_space", "public", path="/")
            log_session(
                user["name"],
                request.remote_addr,
                ";".join(request.remote_route),
                "登录",
                "应用",
                "user:%s,isDev:%s,eng:%s,app:[%s]" % (
                    user["name"], ret.get('isadmin', ''), ret.get('pot', ''), ret.get('nav', '')),
                "成功",
                ""
            )
            return json.dumps(
                {"success": True, "fbi_session": session, "portal": eng, "nav": ret.get('nav', ''),
                 "loginday": loginday, "initial": initial})
        elif auth2_code == 0:
            log_session(
                user["name"],
                request.remote_addr,
                ";".join(request.remote_route),
                "登录",
                "应用",
                "user:%s,auth_key:%s" % (user["name"], pwd),
                "失败",
                "验证失败，请确认用户名和密码有效再登录!"
            )
            raise Exception("验证失败，请确认用户名和密码有效再登录!")
        else:
            log_session(
                user["name"],
                request.remote_addr,
                ";".join(request.remote_route),
                "登录",
                "应用",
                "user:%s" % (user["name"]),
                "失败",
                "验证失败，您的ip不允许登陆该账户!"
            )
            raise Exception("验证失败，您的ip不允许登陆该账户!")
    except Exception as e:
        try:
            # add by gjw on 20180302
            if ssdb0.exists(fail_key) == "0":  # 不存在
                ssdb0.set(fail_key, 1)
                ssdb0.expire(fail_key, lock_times)
            else:
                ssdb0.incr(fail_key, 1)  # 存在加1
                ssdb0.expire(fail_key, lock_times)
        except Exception as e2:
            return '{"success":false,"failed_session":"%s","err":"应用认证出错:%s-%s"}' % (
            traceback.format_exc(), e, e2)
        return '{"success":false,"err":"%s"}' % (e)


# get SN码
@route('/verify_SN')
def get_SN():
    ret = check_session(request, response)
    if ret != 0:
        return "{}"
    sn = get_key("SN")
    if sn == "":
        return get_key("PK")
    else:
        return '{"success":1}'


# 授权状态
@route('/aks')
def get_aks():
    ret = check_session(request, response)
    if ret != 0:
        return "{}"
    x = get_key("PK")
    y = get_key("SN")
    aks = yyy(x, y)
    return "{'state':%s}" % (aks[0])


# 授权状态
@route('/days')
def get_days():
    ret = check_session(request, response)
    if ret != 0:
        return "{}"

    days = have_days()
    return "{'days':%s}" % (days)


file_path = {
    "data": "../workspace/",
    "udf": "udf/",
    "fbi": "script/",
    "xlink": "script/xlinks/",
    "ffdb": "ffdb/",
    "lib": "lib/",
    "tpl_word": "../workspace/temp_word/"
}


# 新建XLink脚本
@route('/putxlink', method="POST")
def new_xlink():
    try:
        ret = check_session(request, response)
        if ret != 0:
            raise Exception("没有认证，无法操作！")
        ID = request.params.get("ID")
        meta_name = request.params.get('meta_name')
        meta_desc = request.params.get('meta_desc')
        with open(file_path["fbi"] + "system/xlink.md") as f:
            xlink = f.read()
        now = datetime.now().isoformat()
        with open(file_path["xlink"] + ID + ".xlk", "w") as f:
            f.write(xlink.format(ID=ID, meta_name=meta_name, meta_desc=meta_desc, create_date=now))
        from avenger.xlink import compile_xlk
        compile_xlk(file_path["xlink"] + ID + ".xlk")
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({'success': -1, 'error': e.__str__()})


# 上传文件
@route('/putfile', method="POST")
def putfile():
    try:
        ret = check_session(request, response)
        if ret != 0:
            raise Exception("没有认证，无法操作！")
        ftype = request.params.get("filetype")
        subdir = request.params.get("subdir") or ""
        upload = request.files.get('jUploaderFile')
        nums = upload.raw_filename.rfind(".")
        if (nums == -1): raise Exception("非法的文件!")
        suffix = upload.raw_filename[nums:]
        if suffix not in [".csv", ".txt", ".json", ".zip", ".gz", ".xls", ".xlsx", ".pkl", ".db", ".pyc"
                                                                                                  ".bz2", ".dat",
                          ".mmdb", ".data", ".jpg", ".png", ".jpeg", ".ttc",
                          ".py", ".xml", ".rar", ".pdf", ".fbi", ".list", ".rules", ".xlk", ".xz", ".fat", ".pq"]:
            raise Exception("非法的文件格式！")
        # print ftype,upload.filename,upload.raw_filename,type(upload.raw_filename)
        if suffix == ".xlk":
            subdir = "xlinks/"
            upload.save(file_path[ftype] + subdir, True)
            os.rename(file_path[ftype] + subdir + upload.filename, file_path[ftype] + subdir + upload.raw_filename)
            from avenger.xlink import compile_xlk
            try:
                compile_xlk(subdir + upload.raw_filename)
            except Exception as e:
                raise Exception("%s xlink文件出错 %s" % (upload.raw_filename, e))
        else:
            upload.save(file_path[ftype] + subdir, True)
            os.rename(file_path[ftype] + subdir + upload.filename, file_path[ftype] + subdir + upload.raw_filename)
        if ftype == "fbi":
            try:
                compile_fbi(subdir + upload.raw_filename)
            # send_reload_signal_to_all(upload.raw_filename)
            except Exception as e:
                raise Exception("%s 编译出错 %s" % (subdir + upload.raw_filename, e))
        elif ftype == "lib":
            import subprocess
            ret = subprocess.call(
                ["tar", "-xvf", file_path[ftype] + subdir + upload.raw_filename, "-C", file_path[ftype]])
        else:
            pass
        return "{'success':0,'file_name':'%s'}" % (subdir + upload.raw_filename)
    except Exception as e:
        return json.dumps({'success': -1, 'error': e.__str__()})


image_path = "/opt/openfbi/mPig/html/images/logo/"


# 上传logo图片
@route('/putfile2', method="POST")
def putfile2():
    try:
        ret = check_session(request, response)
        if ret != 0:
            raise Exception("没有认证，无法操作！")
        portal = request.params.get("portal")
        upload = request.files.get('jUploaderFile')
        nums = upload.raw_filename.rfind(".")
        if (nums == -1): raise Exception("非法的文件!")
        upload.save(image_path, True)
        os.rename(image_path + upload.filename, image_path + portal + ".gif")
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({'success': -1, 'error': e.__str__()})


# 上传图片
@route('/putfile3', method="POST")
def putfile3():
    ret = {"success": True}
    try:
        ret2 = check_session(request, response)
        if ret2 != 0:
            raise Exception("没有认证，无法操作！")
        upload = request.files.get('jUploaderFile')
        nums = upload.raw_filename.rfind(".")
        if (nums == -1): raise Exception("非法的文件!")
        if upload.raw_filename[nums:] not in [".gif", ".png", ".jpeg", ".jpg"]:
            raise Exception("非法的文件格式！")
        upload.save(image_path, True)
        ret["filename"] = upload.filename
        df = {"index": [1], "columns": ["image"], "data": [["/images/logo/" + ret["filename"]]]}
        ssdb0.set("IMG:" + ret["filename"], json.dumps(df))
        return json.dumps(ret)
    except Exception as e:
        ret["success"] = False
        ret["error"] = e.__str__()
        return json.dumps(ret)


# 上传文件
@route('/putfile4', method="POST")
def putfile4():
    # 加上时间标记的文件
    try:
        ret = check_session(request, response)
        if ret != 0:
            raise Exception("没有认证，无法操作！")
        a = int(time.time())
        ftype = request.params.get("filetype")
        subdir = request.params.get("subdir") or ""
        upload = request.files.get('jUploaderFile')
        nums = upload.raw_filename.rfind(".")
        if (nums == -1): raise Exception("非法的文件!")
        if upload.raw_filename[nums:] not in [".gif", ".png", ".jpeg", ".jpg"]:
            raise Exception("非法的文件格式！")
        upload.save(file_path[ftype] + subdir, True)
        new_name = upload.raw_filename[0:nums] + "_" + str(a) + upload.raw_filename[nums:]
        os.rename(file_path[ftype] + subdir + upload.filename, file_path[ftype] + subdir + new_name)
        return "{'success':0,'file_name':'%s'}" % (subdir + new_name)
    except Exception as e:
        return json.dumps({'success': -1, 'error': e.__str__()})


# 复制脚本
@route('/cp_fbi', method="POST")
def copy_script():
    try:
        ret = check_session(request, response)
        if ret != 0:
            raise Exception("没有认证，无法操作！")

        check_isadmin(request)

        src_file = request.params.get("src")
        name = request.params.get("obj")
        syss = ["crud", "word_temp", "user_man", "oper_log", "es7_query", "dict"]
        if src_file.find("--") > 0:
            dir_v = src_file.split("--")[0]
            if dir_v in syss:
                src_file = "system/" + src_file
        src_file = src_file.replace("--", "/")
        if name.find("--") > 0:
            os.makedirs(file_path["fbi"] + "/".join(name.split("--")[0:-1]), exist_ok=True)
            name = name.replace("--", "/")
        shutil.copy(file_path["fbi"] + src_file, file_path["fbi"] + name)
        compile_fbi(name)
        # send_reload_signal_to_all(name)
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({'success': -1, 'error': e.__str__()})


# defines的编辑
@route('/DFEditing', method="POST")
def post_DFEditing():
    try:
        ret = check_session(request, response)
        if ret != 0:
            raise Exception("you can't access data!")
        oper = request.params.get("oper")
        if oper == "del":
            key = request.params.get("id")
            value = ""
        else:
            key = request.params.get("key")
            value = request.params.get("value")
        session = get_session(request)
        put_key(key, value, "as", get_user_by_session(session)[0])
        return json.dumps({"success": True})
    except Exception as e:
        return "{'success':false,'err':'%s'}" % (e)


# 在线编辑，保存代码
@route('/put_fbi', method="POST")
def put_fbi():
    try:
        ret = check_session(request, response)
        if ret != 0:
            raise Exception("没有认证，无法保存！")

        user = check_isadmin(request)
        name = request.params.get("name")
        if name[0] == '"' and name[-1] == '"':
            name = name[1:-1]

        if name.startswith("-"): raise Exception("文件名不合法!")
        if name.startswith("/"): raise Exception("文件名不合法!")
        if name.find("..") > 0: raise Exception("文件名不合法!")

        data = request.params.get("data")
        data = base64.b64decode(data.encode("utf8")).decode("utf8")

        if name.find("--") > 0:
            os.makedirs(file_path["fbi"] + "/".join(name.split("--")[0:-1]), exist_ok=True)
            os.makedirs(file_path["ffdb"] + "/".join(name.split("--")[0:-1]), exist_ok=True)
            name = name.replace("--", "/")
        nums = name.rfind(".")
        if (nums == -1): raise Exception("不能识别的脚本文件!")
        # if name[nums:] not in [".fbi",".xlk"] :raise Exception("文件名不合法,只能以.fbi或.xlk结尾!")

        # add by gjw on 2021-0820
        if name.startswith("system"):
            raise Exception("系统脚本,不能在线编辑! [%s]" % (name));

        now = datetime.now().isoformat()[0:19]

        # add by gjw on 2020　考虑增加脚本的版本问题
        if os.path.exists(file_path["fbi"] + name):
            shutil.copy(file_path["fbi"] + name, file_path["ffdb"] + name + "_" + now)

        # 只保留10个
        contents = []
        lines = data.split("\n")
        i = 0
        for line in lines:
            if line.startswith("#LastModifyDate:"):
                if i < 10:
                    contents.append(line)
                    i += 1
            else:
                contents.append(line)
        data = "\n".join(contents)
        with open(file_path["fbi"] + name, "wb+") as f:
            f.write("#LastModifyDate:　{}    Author:   {}\n".format(now, user).encode("utf8"))
            f.write(data.encode("utf8"))

        if name[nums:] == ".xlk":
            from avenger.xlink import compile_xlk
            compile_xlk(name)
        else:
            compile_fbi(name)
        # send_reload_signal_to_all(name)
        return "<font color='green'>保存成功</font>"
    except Exception as e:
        return "<font color='red'>保存出错,%s</font>" % (e)


# #上传模板文件
@route('/put_tempfile', method="POST")
def put_tempfile():
    try:
        ret = check_session(request, response)
        if ret != 0:
            raise Exception("没有认证，无法操作！")
        ftype = request.params.get("filetype")
        subdir = request.params.get("subdir") or ""
        upload = request.files.get('jUploaderFile')
        nums = upload.raw_filename.rfind(".")
        if (nums == -1): raise Exception("非法的文件!")
        destDir = file_path[ftype] + subdir
        dest_abs_dir = os.path.abspath(destDir)
        if not os.path.exists(dest_abs_dir):
            os.makedirs(dest_abs_dir)
        else:
            shutil.rmtree(dest_abs_dir)
            os.makedirs(dest_abs_dir)
        # print ftype,upload.filename,upload.raw_filename,type(upload.raw_filename)
        upload.save(file_path[ftype] + subdir, True)
        filename1 = file_path[ftype] + subdir + upload.filename
        filename2 = file_path[ftype] + subdir + upload.raw_filename
        destDir = file_path[ftype] + subdir
        dest_abs_dir = os.path.abspath(destDir)
        os.rename(filename1, filename2)
        import zipfile
        zf = zipfile.ZipFile(filename2)
        if not ("".join(zf.namelist()).endswith(".docx")):
            shutil.rmtree(dest_abs_dir)
            raise Exception("上传的压缩包必须是docx文件")
        try:
            zf.extractall(path=destDir)
        except RuntimeError as e:
            root_logger.error("zipfile extra error: %s" % (e))
        name1 = file_path[ftype] + subdir + "".join(zf.namelist())
        name2 = file_path[ftype] + subdir + "template.docx"
        os.rename(name1, name2)
        zf.close()
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({'success': -1, 'error': e.__str__()})


"""
上传单个图片文件也可以上传图片压缩包zip
"""


@route('/put_files', method="POST")
def put_images():
    ret = {"success": True}
    try:
        ret2 = check_session(request, response)
        if ret2 != 0:
            raise Exception("没有认证，无法操作！")
        upload = request.files.get('jUploaderFile')

        nums = upload.raw_filename.rfind(".")
        if (nums == -1): raise Exception("非法的文件!")
        if upload.raw_filename[nums:] not in [".gif", ".png", ".jpeg", ".jpg", ".zip"]:
            raise Exception("非法的文件格式！")
        image_names = []
        # 创建一个临时文件夹来处理zip包解压动作
        source_dir = os.path.join(image_path, 'temp_{}'.format(str(int(time.time()))))
        os.makedirs(source_dir)
        # 保存用户上传的zip包
        upload.save(source_dir)
        zip_name = upload.filename
        zip_path = os.path.join(source_dir, zip_name)

        if zipfile.is_zipfile(zip_path):
            # 解压用户上传的zip包
            shutil.unpack_archive(os.path.join(source_dir, zip_name), source_dir)
            # 将图片保存到logo文件夹下面
            for fn in os.listdir(source_dir):
                if fn != zip_name:
                    fp = os.path.join(source_dir, fn)
                    if os.path.isdir(fp):
                        for c in os.listdir(fp):
                            try:
                                shutil.copy2(os.path.join(fp, c), image_path)
                                image_names.append(c)
                            except:
                                pass
                    elif os.path.isfile(fn):
                        shutil.copy2(fp, image_path)
                        image_names.append(fn)
        else:
            shutil.copy2(zip_path, image_path)
            image_names.append(zip_name)
        # 清理
        shutil.rmtree(source_dir)
        ret["filename"] = image_names
        return json.dumps(ret)
    except Exception as e:
        ret["success"] = False
        ret["error"] = e.__str__()
        return json.dumps(ret)


# 保存登录配置
@route('/put_login', method="POST")
def put_login():
    try:
        # add by gjw on 20180422
        ret = check_session(request, response)
        if ret != 0:
            raise Exception("没有认证，无法保存！")

        data = request.params.get("data")
        f = open("/opt/openfbi/mPig/html/bi/login.json", "wb+")
        f.write(data.encode("utf8"))
        f.close()
        return "<font color='white'>保存成功</font>"
    except Exception as e:
        return "<font color='red'>保存失败,%s</font>" % (e)


# 更新cookie
@route('/ch_cookie', method="POST")
def ch_cookie():
    try:
        ret = check_session(request, response)
        if ret != 0:
            raise Exception("没有认证，无法更新！")
        name = request.params.get("k")
        data = request.params.get("v")
        response.set_cookie(name, data, path="/")
        return ""
    except Exception as e:
        return "<font color='red'>失败,%s</font>" % (e)


@route('/run_block', method="POST")
def run_block():
    ret = check_session(request, response)
    if ret != 0:
        return {"prmtv": "block code", "ret": 1, "error": "身份未验证，不能执行！", "action": 0, "result": 0}
    server = "127.0.0.1"
    port = request.params.get("eng") or request.cookies.eng or "9002"

    # 原语
    block_code = request.params.get("block")
    block_code = base64.b64decode(block_code.encode("utf8")).decode("utf8")
    # 处理中文工作区
    work_space = request.params.get("work_space") or request.cookies.work_space or "public"
    if work_space[0] == '"' and work_space[-1] == '"':
        work_space = work_space[1:-1]

    session = get_session(request)

    if server == "127.0.0.1":
        # 本地直接执行需要的是用户，add by gjw on 20171006
        d = local_run_block(server, port, block_code, work_space, get_user_by_session(session)[0])
    else:
        # remote_run 会调用远程机器的remote_run,所以需要session
        d = local_run_block(server, port, block_code, work_space, session)

    d["server"] = server
    d["port"] = port

    if "work_space" in d:
        response.set_cookie("work_space", d["work_space"])
    response.set_cookie("eng", port)
    if "name" in d:
        response.set_cookie("cur_df", d["name"])
    return json.dumps(d)


@route('/run_blocks', method="POST")
def run_blocks():
    # add by gjw on 20200915 增加对后台引擎的同步代码块执行功能
    ret = check_session(request, response)
    if ret != 0:
        return {"prmtv": "block code", "ret": 1, "error": "身份未验证，不能执行！", "action": 0, "result": 0}

    server = "127.0.0.1"
    port = request.params.get("eng") or request.cookies.eng or "9002"

    # 原语
    block_code = request.params.get("block")
    block_code = base64.b64decode(block_code.encode("utf8")).decode("utf8")
    # 处理中文工作区
    work_space = request.params.get("work_space") or request.cookies.work_space or "public"
    if work_space[0] == '"' and work_space[-1] == '"':
        work_space = work_space[1:-1]

    session = get_session(request)
    d = local_run_blocks(server, port, block_code, work_space, get_user_by_session(session)[0])

    d["server"] = server
    d["port"] = port

    if "work_space" in d:
        response.set_cookie("work_space", d["work_space"])
    response.set_cookie("eng", port)
    if "name" in d:
        response.set_cookie("cur_df", d["name"])
    return json.dumps(d)


@route('/run_blockp', method="POST")
def run_blockp():
    session = get_session(request)
    user, y = get_user_by_session(session)
    if user == "":
        return {"prmtv": "", "ret": -1, "error": "身份未验证，不能执行！", "action": 0, "result": 0}

    # 原语
    block_code = request.params.get("block")
    block_code = base64.b64decode(block_code.encode("utf8")).decode("utf8")
    # 处理中文工作区
    work_space = request.params.get("work_space") or request.cookies.work_space or "public"
    if work_space[0] == '"' and work_space[-1] == '"':
        work_space = work_space[1:-1]

    # add by gjw on 20231214 放置参数
    for name, value in request.params.items():
        if name not in ["block", "work_space", "putlog"]:
            fbi_global.put_param(name, value)

    if "putlog" in request.params:
        putlog_ssdb(user, request.params.putlog, request.remote_addr)
    # end for

    ret, error, datas = run_block_in_sync(block_code, work_space, user)
    d = {"prmtv": "", "ret": ret, "error_info": error, 'error_count': ret, "action": 0, "result": [], "datas": datas}
    fbi_global.clear_params()
    # root_logger.info(d)
    if "work_space" in d:
        response.set_cookie("work_space", d["work_space"])
    return json.dumps(d)


# 显示工作区的数据文件
@route('/list_data')
def list_data():
    ret = check_session(request, response)
    if ret != 0:
        return "{}"

    a = os.listdir(file_path['data'])
    b = copy.copy(a)
    for f in b:
        if f.find(".") == 0:
            a.remove(f)
    a.sort()
    d = {"data": a}
    return json.dumps(d)


# Fbi文件的历史列表
@route('/history_fbi', method="GET")
def fbi_history():
    ret = check_session(request, response)
    if ret != 0:
        return "{}"

    filename = request.query.filename
    filename = filename.replace("--", "/")
    a = []
    for filepath in glob.glob(file_path['ffdb'] + "/" + filename + "*"):
        a.append(filepath)

    a.sort(reverse=True)
    return json.dumps(a)


# 返回Fbi文件的历史版本内容
@route('/version_fbi', method="GET")
def fbi_version():
    ret = check_session(request, response)
    if ret != 0:
        return "{}"
    filename = request.query.filename
    with open(filename, "r") as f:
        a = f.read()
    return a


# 返回xlink的运行日志
@route('/xlink_log/<name>', method="GET")
def xlink_log(name):
    ret = check_session(request, response)
    if ret != 0:
        return "{}"
    filename = request.query.filename
    a = []
    try:
        with open(f"/opt/openfbi/fbi-bin/logs/{name}.log", "r") as f:
            for line in f.readlines():
                a.append(json.loads(line))
    except:
        a = []
    a = a[-1000:]
    a.reverse()
    return json.dumps(a)


# 显示工作区的数据文件
@route('/list_data3')
def list_data3():
    ret = check_session(request, response)
    if ret != 0:
        return "{}"
    session = get_session(request)
    user = get_user_by_session(session)[0]
    # 开始
    pids = {}
    ids = []
    no_access_dirs = []  # 不能访问的目录
    i = 0
    ids.append({"id": i, "pId": i, "name": "数据目录", "open": "true", "dir_name": "/", "chkDisabled": "true"})
    pids[file_path['data']] = i
    i += 1
    for path, d, files in os.walk(file_path['data'], True):
        d.sort()
        for name in d:
            dir_name = os.path.join(path, name)[len(file_path['data']):] + "/"
            real_path = os.path.join(path, name)
            if name.find("__") == 0 and name[2:] != user and user != "superFBI":  # 不是自己的私有目录不能添加，superFBI可以看全部
                no_access_dirs.append(os.path.join(path, name))
            else:
                ids.append({"id": i, "pId": pids[path], "name": name, "isParent": "true", "dir_name": dir_name,
                            "url": real_path})
                if os.path.join(path, name) not in pids:
                    pids[os.path.join(path, name)] = i
                i += 1
                if i >= 2048: break
        # endif
        # endfor
        files.sort()
        for filename in files:
            if filename.find(".") != 0 and path not in no_access_dirs:
                real_path = os.path.join(path, filename)
                filesize = os.path.getsize(real_path) / 1024 / 1024
                ids.append(
                    {"id": i, "pId": pids[path], "name": "%s [%sM]" % (filename, round(filesize, 2)), "url": real_path})
                i += 1
                if i >= 2048: break
        if i >= 2048: break
    # end for
    # end for
    d = {"data": ids}
    return json.dumps(d)


# 显示工作区的数据文件
@route('/list_data2')
def list_data2():
    ret = check_session(request, response)
    if ret != 0:
        return "{}"
    session = get_session(request)
    user = get_user_by_session(session)[0]

    # 开始
    ids = []
    nodeid = request.query.nodeid

    if nodeid == None or nodeid == "":
        nodeid = 0
        ids.append({"id": 0, "pId": nodeid, "name": "数据目录", "open": "true", "dir_name": "/", "chkDisabled": "true"})
        i = 1
        node = ""
    else:
        nodeid = int(nodeid)
        i = nodeid * 1000
        node = request.query.node

    path = file_path['data'] + node

    dir_list = []
    file_list = []
    for filename in os.listdir(path):
        real_path = os.path.join(path, filename)
        if os.path.isdir(real_path):
            dir_list.append(filename)
        else:
            file_list.append(filename)
    dir_list.sort()
    file_list.sort()

    filelist = dir_list + file_list

    for filename in filelist:
        real_path = os.path.join(path, filename)
        if os.path.isdir(real_path):
            dir_name = real_path[len(file_path['data']):] + "/"
            ids.append(
                {"id": i, "pId": nodeid, "name": filename, "isParent": "true", "dir_name": dir_name, "url": real_path})
            i += 1
        else:
            if filename.find(".") != 0:
                filesize = os.path.getsize(real_path) / 1024 / 1024
                ids.append(
                    {"id": i, "pId": nodeid, "name": "%s [%sM]" % (filename, round(filesize, 2)), "url": real_path})
                i += 1
    # end for
    d = {"data": ids}
    return json.dumps(d)


# 显示所有脚本
@route('/list_fbi')
def list_fbi():
    ret = check_session(request, response)
    if ret != 0:
        return "{}"
    session = get_session(request)
    user = get_user_by_session(session)[0]
    # 开始
    pids = {}  # 父节点
    ids = []  # 所有节点
    no_access_dirs = []  # 不能访问的目录
    i = 0
    ids.append({"id": i, "pId": i, "name": "脚本目录", "open": "true", "dir_name": "/", "chkDisabled": "true"})
    pids[file_path['fbi']] = i
    i += 1
    for path, d, files in os.walk(file_path['fbi'], True):
        d.sort()
        for name in d:
            dir_name = os.path.join(path, name)[len(file_path['fbi']):] + "/"
            if name.find("__") == 0 and name[2:] != user and user != "superFBI":  # 不是自己的私有目录不能添加,superFBI可以看全部
                no_access_dirs.append(os.path.join(path, name))
            else:
                ids.append({"id": i, "pId": pids[path], "name": name, "isParent": "true", "dir_name": dir_name})
                if os.path.join(path, name) not in pids:
                    pids[os.path.join(path, name)] = i
                i += 1
        # endif
        files.sort()
        for filename in files:
            if path not in no_access_dirs:
                ids.append({"id": i, "pId": pids[path], "name": filename,
                            "url": "/db/dls/" + os.path.join(path, filename)[7:].replace("/", "--"),
                            "target": "_blank"})
                i += 1
    # endfor
    # endfor
    d = {"data": ids}
    return json.dumps(d)


# 根据关键字搜索脚本内容
@route('/search_fbi', method="POST")
def search_fbi():
    ret = check_session(request, response)
    if ret != 0:
        return "{}"
    session = get_session(request)
    user = get_user_by_session(session)[0]
    key_word = request.params.key_word

    # 开始
    no_access_dirs = []  # 不能访问的目录
    result = []  # 结果列表

    for path, d, files in os.walk(file_path['fbi'], True):
        d.sort()
        for name in d:  # 目录
            if name.find("__") == 0 and name[2:] != user and user != "superFBI":  # 不是自己的私有目录不能添加,superFBI可以看全部
                no_access_dirs.append(os.path.join(path, name))
        # endif
        files.sort()
        for filename in files:  # 文件
            if path not in no_access_dirs:
                # ids.append({"id":i,"pId":pids[path],"name":filename,"url":"/db/dls/"+os.path.join(path, filename)[7:].replace("/","--"),"target":"_blank"})
                with open(os.path.join(path, filename)) as f:
                    try:
                        lines = f.readlines()
                        file_hits = []
                        for i, line in enumerate(lines):
                            if line.find(key_word) >= 0:
                                file_hits.append({"num": i, "line": line})
                        if len(file_hits) > 0:
                            mtime = os.path.getmtime(os.path.join(path, filename))
                            result.append({"name": filename, "url": os.path.join(path, filename)[7:].replace("/", "--"),
                                           "hits": file_hits, "mtime": mtime})
                    except:
                        pass
            # end with
    # endfor
    # endfor
    result.sort(key=lambda x: x["mtime"], reverse=True)
    return json.dumps(result)


# 根据脚本的修改时间展示脚本列表
@route('/modified_fbi')
def modified_fbi():
    ret = check_session(request, response)
    if ret != 0:
        return "{}"
    session = get_session(request)
    user = get_user_by_session(session)[0]

    # 开始
    no_access_dirs = []  # 不能访问的目录
    result = []

    for path, d, files in os.walk(file_path['fbi'], True):
        d.sort()
        for name in d:  # 目录
            if name.find("__") == 0 and name[2:] != user and user != "superFBI":  # 不是自己的私有目录不能添加,superFBI可以看全部
                no_access_dirs.append(os.path.join(path, name))
        # endif
        files.sort()
        for filename in files:  # 文件
            if path not in no_access_dirs:
                # ids.append({"id":i,"pId":pids[path],"name":filename,"url":"/db/dls/"+os.path.join(path, filename)[7:].replace("/","--"),"target":"_blank"})
                with open(os.path.join(path, filename)) as f:
                    try:
                        line = f.readline()
                        file_hits = []
                        file_hits.append({"num": 1, "line": line})
                        mtime = os.path.getmtime(os.path.join(path, filename))
                        result.append({"name": filename, "url": os.path.join(path, filename)[7:].replace("/", "--"),
                                       "hits": file_hits, "mtime": mtime})
                    except:
                        pass
            # end with
    # endfor
    # endfor
    result.sort(key=lambda x: x["mtime"], reverse=True)
    return json.dumps(result)


def local_run(host, port, prmtv, work_space="public", user=""):
    d = {"ret": 0, "error": ""}
    try:
        http = urllib3.PoolManager(timeout=1200.0)
        if user == None or user == "":
            user = "system"
        q = {"prmtv": prmtv, "work_space": work_space, "user": user}
        url = 'http://%s:%s/AI?%s' % (host, port, urlencode(q))
        r = http.request("GET", url)
        if r.status == 200:
            d = json.loads(r.data.decode())
        else:
            d["error"] = "server retun status %s" % (r.status)
            d["ret"] = 1
    except Exception as e:
        # logger.error(traceback.format_exc())
        d["prmtv"] = prmtv
        d["error"] = "remote run has error %s" % (e)
        d["ret"] = 1
    return d


def local_runp(host, port, prmtv, work_space="public", user="sys"):
    # 同步调用，支持push原语的结果
    try:
        ret, error, mresult, datas, cost = run_command2(work_space, prmtv, user)
        d = {"Cost": cost, "ret": ret, "error": error, 'error_count': ret, "action": 0, "result": mresult,
             "datas": datas}
    except Exception as e:
        root_logger.error("execp error: %s" % (e))
        te = traceback.format_exc()
        root_logger.error(te)
    return d


# 语句块调用
def local_run_block(host, port, prmtv, work_space="public", user=""):
    d = {}
    try:
        http = urllib3.PoolManager(timeout=1200.0)
        if user == None or user == "":
            user = "sys"
        q = {"block": prmtv, "work_space": work_space, "user": user}
        url = 'http://%s:%s/run_block2' % (host, port)
        r = http.request("POST", url, q)
        if r.status == 200:
            d = json.loads(r.data.decode())
        else:
            d["error"] = "server retun status %s" % (r.status)
            d["data"] = r.data.decode()
            d["ret"] = 1
    except Exception as e:
        # logger.error(traceback.format_exc())
        d["prmtv"] = prmtv
        d["error"] = "remote run has error %s" % (e)
        d["ret"] = 1
    return d


# 多行语句调用
def local_run_blocks(host, port, prmtv, work_space="public", user=""):
    d = {}
    try:
        http = urllib3.PoolManager(timeout=1200.0)
        if user == None or user == "":
            user = "sys"
        q = {"block": prmtv, "work_space": work_space, "user": user}
        url = 'http://%s:%s/run_blocks2' % (host, port)
        r = http.request("POST", url, q)
        if r.status == 200:
            d = json.loads(r.data.decode())
        else:
            d["error"] = "server retun status %s" % (r.status)
            d["data"] = r.data.decode()
            d["ret"] = 1
    except Exception as e:
        # logger.error(traceback.format_exc())
        d["prmtv"] = prmtv
        d["error"] = "remote run has error %s" % (e)
        d["ret"] = 1
    return d


# 添加用户
@route('/adduser', method="POST")
def adduser():
    data = request.params.get("data")
    isadd = request.params.get("isadd")
    user = json.loads(data)
    if "fbi_session" in user:
        session = user["fbi_session"]
    else:
        session = get_session(request)
    fbi_session = "fbi_session:%s" % (session)
    if ssdb0.exists(fbi_session) == "0": return "you can't access data!"
    try:
        if isadd == "true":
            if user["isadmin"] == "Y" and fbi_user_mgr.get_user_count() > fbi_global.size:
                return '{"success":false,"error":"分析-开发人员超出最大用户数限制!"}'
            fbi_user_mgr.add_user(user)
        else:
            fbi_user_mgr.update_user(user)
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({"success": False, "error": e.__str__()})


# 删除用户
@route('/deluser/<name>')
def deluser(name):
    ret = check_session(request, response)
    if ret != 0:
        return ret
    try:
        fbi_user_mgr.del_user(name)
        fbi_eng_mgr.revoke_user_eng(name)
        return json.dumps({"success": True, "user": name})
    except Exception as e:
        return json.dumps({"success": False, "error": e.__str__()})


# 用户时候存在
@route('/haveuser/<name>')
def haveuser(name):
    ret = check_session(request, response)
    if ret != 0:
        return ret
    try:
        ret = fbi_user_m
have_user(name)
        return json.dumps({"success": True, "ishave": ret})
    except Exception as e:
        return json.dumps({"success": False, "error": e.__str__()})


# add by gjw on 20201023,当前用户的用户信息
@route('/userinfo')
def userinfo():
    ret = check_session(request, response)
    if ret != 0:
        return "{}"
    session = get_session(request)
    try:
        cur_user_name, isAdmin = get_user_by_session(session)
        if isAdmin == "Y":
            userinfo = {"name": cur_user_name}
            userinfo["SysRole_Data"] = ""
        else:
            userinfo = fbi_user_mgr.get_user_by_name(cur_user_name)
            SysRole = ssdb0.get(b64("SysRole:%s" % (userinfo["sys_role"])))
            if SysRole:
                userinfo["SysRole_Data"] = json.loads(SysRole)
            else:
                userinfo["SysRole_Data"] = ""
        return json.dumps(userinfo)
    except Exception as e:
        return json.dumps({"success": False, "error": e.__str__()})


# 代理原语函数
@route('/abci', method=["GET", "POST"])
def abci():
    session = get_session(request)
    response.set_header("Content-Type", 'application/json; charset=UTF-8')
    user, isadmin = get_user_by_session(session)
    if user == "":
        return json.dumps({"prmtv": "", "ret": 1, "error": "身份未验证，不能执行！", "action": 0, "result": 0})

    port = request.params.eng or request.cookies.eng or "9002"
    # 原语
    prmtv = request.params.prmtv
    # 处理中文工作区
    work_space = request.params.work_space or request.cookies.work_space or "public"
    if work_space[0] == '"' and work_space[-1] == '"':
        work_space = work_space[1:-1]

    server = "127.0.0.1"

    if isadmin == "Y":  # 管理员有引擎
        d = local_run(server, port, prmtv, work_space, user)
        if "work_space" in d:
            response.set_cookie("work_space", d["work_space"], path="/")
        response.set_cookie("eng", port)
        if "cur_df" in d:
            response.set_cookie("cur_df", d["cur_df"], path="/")
    else:  # 非开发人员
        d = {}
        if prmtv.startswith("run "):  # 使用后台定时器计算
            prmtv_new = "settimer sys1 by '* * * * * *' {}".format(prmtv)
            d = local_run(server, port, prmtv_new, work_space, user)
            # 为了让页面不出错
            d["result"] = [{"TI": "140390393317120@9002", "ST": "2022-10-13T10:12:39.388950",
                            "FID": "140390393317120:2022-10-13T10:12:39.388950"}]
        elif prmtv.startswith("check "):  # 统一返回运行结束
            d = {"prmtv": "", "ret": 0, "error": "", "action": 0,
                 "result": {"find": True, "isAlive": False, "end_time": "", "progress": "0/0", "command": "FAST_MODE",
                            "cost": "", "error_count": 0, "error_info": "", "depth": 1, "alive_tasks": 1}}
        else:
            d = {"prmtv": "", "ret": 1, "error": "非开发员不能执行其他原语！", "action": 0, "result": 0}
    return json.dumps(d)


# 门户调用脚本的进入点
@route('/abcip', method=["GET", "POST"])
def abcip():
    session = get_session(request)
    response.set_header("Content-Type", 'application/json; charset=UTF-8')

    # 原语
    prmtv = request.params.prmtv
    # 处理中文工作区
    work_space = request.params.work_space or request.cookies.work_space or "public"
    if work_space[0] == '"' and work_space[-1] == '"':
        work_space = work_space[1:-1]

    if prmtv.find("check task") != -1:
        d = {"prmtv": "", "ret": 0, "error": "", "action": 0, "result": {"isAlive": "false"}}
    else:
        try:
            user, isadmin = get_user_by_session(session)
            if user == "":
                return json.dumps({"prmtv": "", "ret": 1, "error": "身份未验证，不能执行！", "action": 0, "result": 0})

            # add by gjw on 2020-1223 增加对执行脚本的权限校验,管理员不做检查,便于进行开发操作
            if isadmin == "N" or user != "superFBI":
                try:
                    SysRule = ssdb0.get("SysRule:scripts:%s" % (user))
                    SysRule_dict = json.loads(SysRule)
                except:
                    SysRule_dict = {}
            else:
                SysRule_dict = {}

            # add by gjw on 20231214 放置参数
            for name, value in request.params.items():
                if name not in ["prmtv", "work_space", "putlog"]:
                    fbi_global.put_param(name, value)
            # end for

            # 运行脚本
            ret, error, mresult, datas, cost = run_command2(work_space, prmtv, user, SysRule_dict)
            d = {"Cost": cost, "ret": ret, "error_info": error, 'error_count': ret, "action": 0, "result": mresult,
                 "datas": datas}
            if "putlog" in request.params:
                if ret == 0:
                    operate_result = "成功"
                    failed_reason = " "
                else:
                    operate_result = "失败"
                    failed_reason = error
                putlog_ssdb(user, request.params.putlog, request.remote_addr, operate_result, failed_reason)

            fbi_global.clear_params()
        except Exception as e:
            root_logger.error("execp error: %s" % (e))
            te = traceback.format_exc()
            root_logger.error(te)
    return json.dumps(d)


@route("/")
def index():
    return "身份未验证，不能执行!"


@route('/static/<filepath:path>')
def server_static(filepath):
    ret = check_session(request, response)
    if ret != 0:
        return "没有认证,不能访问!"
    return static_file(filepath, root="./static")


@route('/dbd/<filepath:path>')
def server_dbd(filepath):
    ret = check_session(request, response)
    if ret != 0: return redirect("/auth.h5")
    return static_file(filepath, root="/opt/openfbi/mPig/html/dbd")


@route('/fbi/<filepath:path>')
def server_fbi(filepath):
    if filepath in ["login.h5", "css/newlogin.css", "js/login.js"]:
        return static_file(filepath, root="/opt/openfbi/mPig/html/fbi")
    else:
        ret = check_session(request, response)
        if ret != 0: return redirect("/auth.h5")
    return static_file(filepath, root="/opt/openfbi/mPig/html/fbi")


@route('/bi/<filepath:path>')
def server_bi(filepath):
    if filepath in ["login.json", "index.h5", "index.js"]:
        return static_file(filepath, root="/opt/openfbi/mPig/html/bi")
    else:
        ret = check_session(request, response)
        if ret != 0: return redirect("/auth.h5")
    return static_file(filepath, root="/opt/openfbi/mPig/html/bi")


@route('/future/<filepath:path>')
def server_future(filepath):
    ret = check_session(request, response)
    if ret != 0: return redirect("/auth.h5")
    return static_file(filepath, root="/opt/openfbi/mPig/html/future")


# 下载数据文件
@route('/workspace/<filepath:path>')
def download_workspace(filepath):
    ret = check_session(request, response)
    if ret != 0: return redirect("/auth.h5")
    session = get_session(request)
    user = get_user_by_session(session)[0]
    if filepath.find("__") == 0 and filepath[2:len(user) + 2] != user:
        ret = 1
        error = "你 [%s] 没有权限下载该文件!" % (user)
        loglog(user, request.remote_addr, ";".join(request.remote_route), "下载数据", "门户", \
               filepath, "失败", error)
        return error
    loglog(user, request.remote_addr, ";".join(request.remote_route), "下载数据", "门户", \
           filepath, "成功", "")
    return static_file(filepath, root=file_path['data'], download=True)


# 下载fileinfo的文件的服务
@route('/download/<filepath:path>')
def download_workspace(filepath):
    ret = check_session(request, response)
    if ret != 0: return redirect("/auth.h5")
    session = get_session(request)
    file_name = request.query.get("filename")
    file_name = quote(file_name)
    user = get_user_by_session(session)[0]
    loglog(user, request.remote_addr, ";".join(request.remote_route), "下载文件", "门户", \
           filepath, "成功", "")
    return download_file(filepath, root=file_path['data'], download_name=file_name)


# 删除数据文件
@route('/remove_data')
def remove_workspace():
    ret = check_session(request, response)
    if ret != 0:
        return "{}"
    session = get_session(request)
    user = get_user_by_session(session)[0]
    filepath = request.query.filename
    if filepath.find("__") == 0 and filepath[2:len(user) + 2] != user:
        error = "你 [%s] 没有权限删除该文件!" % (user)
        return json.dumps({"success": False, "error": error})
    if filepath.find("../workspace") != 0:
        return json.dumps({"success": False, "error": "无法删除文件!"})
    if filepath[len("../workspace"):].find("../") >= 0:
        return json.dumps({"success": False, "error": "无法删除文件!"})
    if os.path.isdir(filepath):
        os.removedirs(filepath)
    else:
        os.remove(filepath)
    return json.dumps({"success": True})


# 删除fbi文件
@route('/remove_fbi')
def remove_fbi():
    try:
        ret = check_session(request, response)
        if ret != 0:
            return "{}"
        user = check_isadmin(request)
        filepath = request.query.filename
        filepath = filepath[len("/fbi_id/"):].replace("--", "/")
        if filepath.find("__") == 0 and filepath[2:len(user) + 2] != user:
            error = "你 [%s] 没有权限删除该文件!" % (user)
            return json.dumps({"success": False, "error": error})
        if filepath.find("../") >= 0:
            return json.dumps({"success": False, "error": "无法删除文件!"})
        if filepath.endswith(".xlk"):
            xlnk_name = filepath[filepath.rfind("/"):-4]
            os.remove(f"/opt/openfbi/fbi-bin/addones/streams/{xlnk_name}.py")
        os.remove(file_path['fbi'] + filepath)
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({"success": False, "error": e.__str__()})


# 创建数据目录
@route('/mkdir_data')
def mkdir_data():
    ret = check_session(request, response)
    if ret != 0:
        return "{}"
    session = get_session(request)
    user = get_user_by_session(session)[0]
    filepath = request.query.filename
    filepath = filepath.replace("--", "/")
    os.makedirs(file_path['data'] + filepath, exist_ok=True)
    return json.dumps({"success": True})


# 查看fbi脚本文件
@route('/fbi_script/<fbiname>')
def get_fbi_file(fbiname):
    try:
        ret = check_session(request, response)
        if ret != 0:
            return "没有认证，不能下载！"

        user = check_isadmin(request)

        if fbiname.find("__") == 0 and fbiname[2:len(user) + 2] != user and user != "superFBI":
            ret = 1
            error = "你 [%s] 没有权限查看该脚本!" % (user)
            return error

        if fbiname[0] == '"' and fbiname[-1] == '"':
            fbiname = fbiname[1:-1]
        try:
            fbiname = fbiname.replace("--", "/")
            f = open(file_path["fbi"] + fbiname)
            data = f.read()
            f.close()
            return data
        except:
            return "#FBI脚本文件\n#文件名: %s\n#作者: %s\n#创建时间: %s\n" % (
            fbiname, user, datetime.now().isoformat()[0:19])
    except Exception as e:
        return e.__str__()


# 下载fbi脚本文件
@route('/dls/<fbiname>')
def download_fbi_file(fbiname):
    try:
        ret = check_session(request, response)
        if ret != 0:
            return "没有认证，不能下载！"
        user = check_isadmin(request)
        if fbiname.find("__") == 0 and fbiname[2:len(user) + 2] != user and user != "superFBI":
            ret = 1
            error = "你 [%s] 没有权限查看该脚本!" % (user)
            return error

        if fbiname[0] == '"' and fbiname[-1] == '"':
            fbiname = fbiname[1:-1]
        fbiname = fbiname.replace("--", "/")
        return static_file(fbiname, root=file_path['fbi'], download=True)
    except Exception as e:
        return e.__str__()


# 高亮显示脚本的html
@route('/fbi_id/<name>')
def fbi_id(name):
    ret = check_session(request, response)
    if ret != 0:
        raise Exception("没有认证，无法查看！")
    return redirect("/static/fbi-view.html?name=%s" % (name))


@route('/base_pic', method="POST")
def base_pic():
    ret = check_session(request, response)
    if ret != 0:
        return "{}"
    try:
        import base64
        data = request.params.get("data")
        data_json = json.loads(data)
        key = data_json["key"]
        base64_value = data_json["base64"]
        pic_base_path = file_path["data"] + "pic_base/"
        if not os.path.exists(pic_base_path):
            os.makedirs(pic_base_path)
        with open(pic_base_path + key + ".txt", "w") as f:
            f.write(base64_value)
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({"success": False, "error": e.__str__()})


# 显示对应的word模板的图片列表
@route('/list_word_pics/<id>')
def list_word_pics(id):
    ret = check_session(request, response)
    if ret != 0:
        return "{}"
    # root_logger.info(file_path['tpl_word']+id)
    a = os.listdir(file_path['tpl_word'] + id)
    # root_logger.info(a)
    b = []
    for f in a:
        if f.endswith(".png") or f.endswith(".jpg") > 0:
            b.append(f)
    b.sort()
    d = {"data": b}
    return json.dumps(d)


app = default_app()

if __name__ == "__main__":
    run(server="paste", host='0.0.0.0', port=9999, debug=False)


