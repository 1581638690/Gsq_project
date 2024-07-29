import ujson
from datetime import timedelta
import datetime


def session_action_relation(sessionid, interface_url, action_dict, o, url_type, url_list, move_interface=None):
    current_time = datetime.datetime.now()

    # 清理超过24小时的sessionid
    to_delete = []
    for sid, value in action_dict.items():
        if "timestamp" in value and current_time - value["timestamp"] > timedelta(hours=12):
            to_delete.append(sid)

    for sid in to_delete:
        del action_dict[sid]

    founds = False

    update_action = False
    if url_type == "详情" and sessionid:
        url = o.get("url")
        if sessionid not in action_dict:  # 不存在与字典中，则
            # 检查当前接口是否匹配给定的URL
            if url == interface_url:  # 起始接口，若起始接口都没有就无法进行存储
                action_dict[sessionid] = {url: [o], "timestamp": current_time}  # 这个接口不需要进行存储
                founds = True
            else:
                if move_interface.get("search", "") and move_interface.get("search", "") == url:
                    # 如果该接口存在，就需要判断
                    founds = remove_one_search(o)
                elif move_interface.get("YjxxList") and move_interface.get("YjxxList", "") == url:
                    founds = remove_par_judge(o)

        else:
            # 该用户存在获取user_actions
            user_actions = action_dict[sessionid]
            # 获取到o的url，判断interface_url是否与o的url一致，如果一致，则表示是同一个接口,session已经存在，所以需要将其进行清空，
            # url_lst = user_actions[url]
            if interface_url == url and interface_url in user_actions:
                # 如果接口相同，就将user_actions 置为空，因为已经点击其他详情数据了
                user_actions[url] = []
                user_actions[url].append(o)

                # user_actions.setdefault(url, []).append(o)
                action_dict[sessionid] = user_actions
                founds = True
            else:
                # 判断detail是否为详情
                if move_interface.get("search", "") and move_interface.get("search", "") in url:
                    # 如果该接口存在，就需要判断
                    founds = remove_one_search(o)
                elif move_interface.get("YjxxList") and move_interface.get("YjxxList", "") in url:
                    founds = remove_par_judge(o)
                else:
                    url_lst = user_actions.get(interface_url, [])
                    current_request_body = o.get("request_body", "")
                    try:
                        current_request_body = ujson.loads(current_request_body)
                    except:
                        current_request_body = current_request_body

                    # 获取当前新进接口的表名称
                    current_table_name = ""

                    if isinstance(current_request_body, dict):
                        current_table_name = current_request_body.get("tableName", "")

                    # 跟历史记录进行对比，若出现重复的表名则更新改信息
                    for idx, d_url in enumerate(url_lst):
                        history_url = d_url.get("url", "")
                        # 获取历史记录请求体，获取历史表名
                        history_request_body = d_url.get("request_body", "")
                        try:
                            history_request_body = ujson.loads(history_request_body)
                        except:
                            history_request_body = history_request_body
                        if isinstance(history_request_body, dict):
                            history_table_name = history_request_body.get("tableName", "")
                            if current_table_name == history_table_name and current_table_name != "":
                                url_lst[idx] = o
                                founds = False
                                update_action = True
                                break
                            elif history_url == url and url != "" and any(
                                    u in url for u in url_list):  # 判断接口相同，且接口存在自制的url_list中，才进入判断
                                if current_request_body != history_request_body:
                                    url_lst[idx] = o
                                    founds = False
                                    update_action = True
                                    break
                        else:
                            continue

                if not founds and not update_action:
                    user_actions.setdefault(interface_url, []).append(o)
    else:
        founds = True
    return action_dict, founds


def par_judge(o):
    request_body = o.get("request_body", "")
    if request_body:
        if "deptName" in request_body:  # deptName表示翻页操作，True就是要单独退出来，False就是要进入到列表中
            # 这个就表示是翻页操作，而不是详情里面的操作，所以翻页操作需要进行推出
            return True
    return False


def remove_one_search(o):
    request_body = o.get("request_body", "")
    if "business_time.keyword" in request_body:
        return False

    try:
        request_body = ujson.loads(request_body)
    except Exception as e:
        request_body = request_body
    if isinstance(request_body, dict):
        page = request_body.get("page")
        size = request_body.get("size")

        if page == 1 and size == 4:
            return False

    return True


def remove_par_judge(o):
    parameter = o.get("parameter", "")
    if "page=0" in parameter:
        return False
    return True


# 2024/6/4 根据用户调用的行为操作接口，获取接口数据信息，并对存储的接口信息进行获取对比
def retrieve_forward(action_dict, o, session_id, interface_url):
    """
    :param action_dict: 行为链条存储信息
    :param url: 接口
    :param session_url:用户的会话ID
    :param request_body: 请求体
    :return:
    """
    founds_url = False
    url = o.get("url")
    if url == '/hsdsh/public/api/flowMonitoring':
        request_body = o.get("request_body")
        current_event = o.get("event")
        current_ret_res = o.get("res")

        try:
            request_body = ujson.loads(request_body)
        except:
            request_body = request_body
        current_topic = request_body.get("topic", "")
        current_table = request_body.get("tableName", "")  # 当前点击标签的表名称
        current_modelName = request_body.get("modelNmae", "")  # 当前点击模块的标签名称
        current_subModel = request_body.get("subModel", "")  # 当前模块子模块标签名称
        current_eventId = request_body.get("eventId", "")
        current_serNumber = request_body.get("serNumber", "")
        current_apiName = request_body.get("api", "")
        # 首先判断点击的是不是一级模块标签  不是子模块的条件 序号为-1 事件ID为空，这个就是人口跟企业的详情一级模块
        if not current_eventId and current_serNumber == -1 and current_modelName != "基本信息":
            # 子模块跟事件ID必须有一个存在,若不存在，则是一级模块标签，直接输出操作行为
            founds_url = True

        else:
            # 判断session_id存不存在与队列当中
            if session_id in action_dict:
                # 获取到当前行为链的详情操作
                detail = action_dict.get(session_id, {})
                if detail:
                    # 获取当前行为链条起始接口的详情数据
                    face_data = detail.get(interface_url, [])

                    # 循环接口数据信息
                    for dd in face_data:
                        fetch_url = dd.get("url", "")
                        subName = dd.get("subName", "")
                        # 获取请求体
                        fetch_request_body = dd.get("request_body", "")
                        try:
                            fetch_request_body = ujson.loads(fetch_request_body)
                        except:
                            fetch_request_body = fetch_request_body

                        # 获取响应体
                        fetch_response_body = dd.get("response_body", "")
                        try:
                            fetch_response_body = ujson.loads(fetch_response_body)
                        except:
                            fetch_response_body = fetch_response_body

                        parameter = dd.get("parameter", "")
                        event_id = ""
                        # 对参数进行分割
                        par_lst = parameter.split("&")
                        for par in par_lst:
                            if "id" in par:
                                event_id = par.split("=")[1]
                                break

                        # 判断当前行为链条的起始接口的请求体表名是否与当前接口的请求体表名一致
                        # 企业基本上都存在表名，不存在表名就一个
                        fetch_table = ""
                        if isinstance(fetch_request_body, dict):
                            fetch_table = fetch_request_body.get("tableName", "")

                        # 形成子条件规则
                        condition1 = (fetch_table == current_table and current_table)
                        condition2 = (((current_apiName in fetch_url) or (
                                fetch_url in current_apiName)) and current_apiName)
                        condition3 = (current_subModel == subName and current_subModel)
                        event_conditon = (current_eventId == event_id and current_eventId)
                        jiben_con = (
                                current_modelName == "基本信息" and current_serNumber == -1 and current_subModel == "")

                        # 第一种情况，表名相同或者 事件ID相同，且存在子模块，且序号不为-1 这就是子模块点击序号操作
                        if event_conditon and current_serNumber == -1:
                            event_response_body = dd.get("response_body", "")
                            # 将当前response_body 替换到当前响应体中
                            o["response_body"] = event_response_body
                            founds_url = True
                            break
                        elif jiben_con:
                            current_table = "gj_qxb_qyjbxxb"
                            if fetch_table == current_table:
                                fetch_data = fetch_response_body.get("data", "")
                                if fetch_data:
                                    o["res"] = fetch_data[0]
                                founds_url = True
                                break
                        elif ((
                                      condition1 or condition2) or condition3) and current_subModel and current_serNumber != -1:
                            # 如果两个相等就将当前o的响应体等于表中信息

                            # 获取当前序号的结果信息
                            if not isinstance(fetch_response_body, dict):
                                continue
                            else:
                                fetch_data = fetch_response_body.get("data", "")
                                # 获取到点击数据序号的详情
                                data_index_detail = fetch_data[current_serNumber - 1]
                                # o["response_body"] = fetch_response_body
                                o["res"] = data_index_detail
                                # 操作参数处理
                                current_event = oper_res("event", dd, current_event)
                                o["event"] = current_event

                                # 返回结果处理
                                # current_ret_res = oper_res("ret_res", dd, current_ret_res)
                                # o["ret_res"] = current_ret_res
                                founds_url = True
                                break

    return o, founds_url


def oper_res(parameters, dd, current_dic):
    fetch_ret_res = dd.get(parameters)
    if fetch_ret_res:
        for ch_ret_res, ret_res in fetch_ret_res.items():
            current_dic.setdefault(ch_ret_res, ret_res)
    return current_dic


def company_basic_info(url, event_dic, basic_dic, url_type):
    """
    处理接口数据，更新基本信息字典.

    :param url: 接口 URL
    :param event_dic: 包含请求体、响应体和其他相关信息的字典
    :param basic_dic: 存储基本信息的字典
    :return: 更新后的基本信息字典
    """
    m_found = False
    parameter = event_dic.get("parameter", "")
    request_body = event_dic.get("request_body", "")

    main_url = "/hsdsh/es/searchForHitList"
    if url_type != "详情":
        return {}, True
    # 处理主接口 /hsdsh/es/searchForHitList
    if url == main_url:
        if main_url not in basic_dic and "企业" in parameter:
            # 记录请求信息，但不返回实际数据
            basic_dic[main_url] = event_dic
            return {}, m_found
        else:

            # 返回空字典，表示还没有完整的数据
            return {}, True

    # 处理详情接口 /hsdsh/peopleEnterprise/selectListForPg
    if url == "/hsdsh/peopleEnterprise/selectListForPg":
        table_name = request_body.get("tableName", "")

        if main_url in basic_dic and table_name == "gj_qxb_qyjbxxb":
            # 获取基本信息的 res
            jbxx_res = event_dic.get("res")
            # 更新 basic_dic 中 main_url 对应的项
            basic_dic[main_url]["res"] = jbxx_res
            # basic_dic[main_url]["url"] = main_url
            m_found = True
            return basic_dic[main_url], m_found

    return {}, True


"""
1.标注接口为详情接口，并对接口中信息进行标注
2.根据标注信息，生成详情接口的详情数据，获取到 event，ret_res, response_body,request_body,url,time,cookie,user_info,account,action,status_msg
3.将信息传入 session_action_relation中，若结果为True则输出接口，若结果为False则表明不是输出结果，需要存储到行为链条action_dict中。
4.获取到系统埋点的接口信息，判断条件是否符合，获取到系统埋点接口信息的请求体中的表名，循环action_dict，找出与之相对应的表名，获取到相应的操作行为和原始数据，然后输出

"""

if __name__ == '__main__':
    url_list = ["/hsdsh/peopleEnterprise/getEnterpriseBidding", "/hsdsh/peopleEnterprise/getPersonMaritalStatus",
                "/hsdsh/peopleEnterprise/getPersonEducationData", "/hsdsh/peopleEnterprise/getPersonMarriageInfo",
                "/hsdsh/peopleEnterprise/getPersonSocialInfo", "/hsdsh/peopleEnterprise/getPersonAccumulationFund",
                "/hsdsh/peopleEnterprise/getPersonVehicleTrafficRecords",
                "/hsdsh/peopleEnterprise/getAccessControlRecords"]
    action_dict = {'c7318a9eaa425684db4052edca008c1b': {'searchForHitList': [
        {'url': 'searchForHitList', '接口事件': '详情', 'sessionid': 'c7318a9eaa425684db4052edca008c1b'},
        {"url": "selectListForPg", "接口事件": "详情", "sessionid": "c7318a9eaa425684db4052edca008c1b",
         "request_body": '{"tableName":"gj_qxb_qydhgsgs","codition":{"eid":""},"page":1,"limit":20}',
         "response_body": '{"code":"请求成功！","呼啦呼啦呼啦"}'},
        {"url": "selectListForPg", "接口事件": "详情", "sessionid": "c7318a9eaa425684db4052edca008c1b",
         "request_body": '{"tableName":"gj_qxb_qyjbxxb","codition":{"eid":""},"page":2,"limit":10}',
         "response_body": '{"code":"请求成功！","data":[{"tiel":1},{"title":2},{}]}'},
        {"url": "http://10.18.95.82.8000/hsdsh/peopleEnterprise/getEnterpriseBidding", "接口事件": "详情",
         "sessionid": "c7318a9eaa425684db4052edca008c1b",
         "request_body": '{"codition":{"eid":""},"page":1,"limit":10}',
         "response_body": '{"code":"0000","data":[{"tiel":2},{"title":2},{}]}'}
    ],
        'timestamp': datetime.datetime(2024, 6, 13, 16, 1, 58, 840615)},

    }
    company_list = [
        {'url': 'searchForHitList', '接口事件': '详情', 'sessionid': 'c7318a9eaa425684db4052edca008c1b'},
        {"url": "selectListForPg", "接口事件": "详情", "sessionid": "c7318a9eaa425684db4052edca008c1b",
         "request_body": '{"tableName":"gj_qxb_qyjbxxb","codition":{"eid":""},"page":2,"limit":10}',
         "response_body": '{"code":"请求成功！","这是第二个"}'}
    ]
    o_list = [
        {"url": "selectListForPg", "接口事件": "详情", "sessionid": "c7318a9eaa425684db4052edca008c1b",
         "request_body": '{"tableName":"gj_qxb_qyjbxxb","codition":{"eid":""},"page":1,"limit":10}',
         "event": {"身份证号": "410422200104025919"}, "ret_res": {},
         "response_body": {"data": [{"title": "法定代表人"}]}},

    ]
    o_list1 = [
        {"url": "http://10.18.95.82.8000/hsdsh/peopleEnterprise/getEnterpriseBidding", "接口事件": "详情",
         "sessionid": "c7318a9eaa425684db4052edca008c1b",
         "request_body": '{"codition":{"eid":""},"page":2,"limit":10}',
         "response_body": '{"code":"0000","data":[{"tiel":3},{"title":4},{}]}'}
    ]
    for o in company_list:
        sessionid = o.get("sessionid")
        interface_url = "searchForHitList"
        move_interface = {"search": "search", "YjxxList": "YjxxList"}
        url_type = o.get("接口事件")

        action_dict, found = session_action_relation(sessionid, interface_url, action_dict, o, url_type, url_list,
                                                     move_interface)

    action_olst = [
        {
            "url": "http://10.18.95.82:8000/hsdsh/public/api/flowMonitoring",
            "sessionid": "c7318a9eaa425684db4052edca008c1b",
            "request_body": {
                "topic": "企业",
                "modelNmae": "招标信息公示",
                "subModel": "招标信息公示",
                "serNumber": 1,
                "tableName": "api/peopleEnterprise/getEnterpriseBidding",
                "eventId": "",
                "api": "http://10.18.95.82.8000/hsdsh/peopleEnterprise/getEnterpriseBidding"
            },
            "app": "10.18.95.82:8000",
            "event": {
                "主体类型": "企业",
                "模块名": "招标信息公示"
            },
            "res": {}
        }
    ]
    for action_o in action_olst:
        session_id = 'c7318a9eaa425684db4052edca008c1b'

        interface_url = 'searchForHitList'
        o, found_url = retrieve_forward(action_dict, action_o, session_id, interface_url)

    basic_dict = {}
    oo_list = [
        {"url": "/hsdsh/es/searchList", "url_type": "详情",
         "parameter": "keyword=徐君&analyzer=false",
         "res": {"事件部门名称": {}}, "founds": True,
         "request_body": {"tableName": "gj_qxb_qyjbxxb", "condition": {"eid": ""}, "page": 1, "limit": 10},
         "response_body": {"code": "0000", "msg": "请求成功", "data": [
             {"actual_capi": "210", "oper_name": "王鑫杰", "format_name": "杭州三富金属材料有限公司",
              "credit_no": "913301055660514050"}]}
         },
        {"url": "/hsdsh/es/searchForHitList", "founds": True, "url_type": "详情",
         "parameter": "index=enterprise_collect_last&id=gsq_data_qydxzcxx_abc&keyword=王鑫&analy=false&topic=企业&tableName=gsq_data_sjcj_qydxzcxx",
         "res": {"公司名称": ["aaaaaaaa"]}, "request_body": "", "response_body": {"code": "0000", "msg": "请求成功"}},
        {"url": "/hsdsh/peopleEnterprise/selectListForPg",
         "parameter": "", "url_type": "详情", "founds": False,
         "res": {}, "request_body": {"tableName": "gj_qxb_zyrygsgsb", "condition": {"eid": ""}, "page": 1, "limit": 10},
         "response_body": {"code": "0000", "msg": "请求成功", "data": [
             {"name": "王峰萍",
              "credit_no": "913301055660514050"}, {"name": "王鑫杰",
                                                   "credit_no": "913301055660514050"}]}
         },
        {"url": "/hsdsh/peopleEnterprise/selectListForPg", "url_type": "详情",
         "parameter": "", "founds": False,
         "res": {"公司名称": ["杭州三富金属材料有限公司"], "社会统一标识": ["913301055660514050"]},
         "request_body": {"tableName": "gj_qxb_qyjbxxb", "condition": {"eid": ""}, "page": 1, "limit": 10},
         "response_body": {"code": "0000", "msg": "请求成功", "data": [
             {"actual_capi": "210", "oper_name": "王鑫杰", "format_name": "杭州三富金属材料有限公司",
              "credit_no": "913301055660514050"}]}
         },
        {"url": "/hsdsh/es/searchForHitList", "url_type": "详情", "founds": True,
         "parameter": "index=enterprise_collect_last&id=gsq_data_qydxzcxx_abc&keyword=王鑫&analy=false&topic=人口&tableName=gsq_data_sjcj_qydxzcxx",
         "res": {"公司名称": ["aaaaaaaa"]}, "request_body": "", "response_body": {"code": "0000", "msg": "请求成功"}},

    ]
    for oo in oo_list:
        url = oo.get("url")
        url_type = oo.get("url_type")
        founds = oo.get("founds")
        res, m_found = company_basic_info(url, oo, basic_dict,
                                          url_type)  # 三种结果 {} True是详情但是不符合条件,{} False是主接口，且第一次访问,{dadad},True是基本信息接口，也获取到了具体信息，返回查看详情接口信息
        if res and m_found:  # {dadad},True
            basic_dict = {}  # 将字典置为空，且当前日志 == res

            oo = res
            founds = True

        if founds and m_found:
            print(oo)
