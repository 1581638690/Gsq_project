import os
import time
import ujson
import pickle
import pandas as pd
from collections import defaultdict
import configparser

# 读取配置文件
path_config = configparser.ConfigParser()
path_config.read('./config.ini')
# path_config.read('config_window.ini')
# 获取字符信息# 获取 start_chars 和 end_chars
start_chars_str = path_config.get('Characters', 'start_chars')
end_chars_str = path_config.get('Characters', 'end_chars')
start_chars = [char.strip() for char in start_chars_str.split(',')]
end_chars = [char.strip() for char in end_chars_str.split(',')]


def classify_data1(condition, datas):
    """
    :param condition: 这几条数据的上下文规则信息
    :param datas: 分类数据
    :return:
    """
    # 获取http日志数据信息
    classified_groups = defaultdict(dict)
    # 获取json日志信息
    json_class_groups = defaultdict(dict)
    # 对原始数据进行上下文分类处理信息
    # 他只有一个信息 一个key值
    for key, value in condition.items():
        for o_data in datas:
            json_entry_data = {"imps": []}
            current_entry_data = {"imps": []}
            idx = o_data.get("idx")
            http_data = o_data["data"]
            imps_lst = o_data["imps"]
            # 获取原始数据中需要的字段信息

            # 获取标识数据信息
            for imp in imps_lst:
                imp_pos = imp.get("imp_pos")  # 标注名称
                imp_name = imp.get("imp_name")  # 标注内容信息
                # 新增识别方法，JSON或者TEXT
                imp_type = imp.get("imp_type")  # 标注的内容信息
                if "JSON" in imp_type:
                    # 如果 JSON存在与imp中，就将JSON 存入json_class_groups中，如果不存在则直接存入字符串识别中
                    if imp_pos in http_data:
                        json_entry_data[imp_pos] = http_data[imp_pos]
                    imp["annotated_index"] = imps_lst.index(imp)
                    json_entry_data["imps"].append(imp)
                    json_class_groups[key].setdefault(idx, json_entry_data)
                else:
                    if imp_pos in http_data:
                        current_entry_data[imp_pos] = http_data[imp_pos]
                    imp["annotated_index"] = imps_lst.index(imp)
                    current_entry_data["imps"].append(imp)
                    # 更新分类数据字典
                    classified_groups[key].setdefault(idx,
                                                      current_entry_data)  # {“测试7”:{"1":{"imps":[],"parameter":""}}}

    return classified_groups, json_class_groups


def data_merge(con, o_data):
    # 调用函数
    classified_groups, json_class_groups = classify_data1(con, o_data)
    cls = {}
    for key, datas in classified_groups.items():  # key:测试7  datas:{"0":{"imps":[],"parameter":""}

        unique_imp_lst = []
        for idx, id_dic in datas.items():  # [data,data]
            # 获取标识信息的详细内容
            imps_list = id_dic["imps"]

            # 判断标识数据是否为空 为空 则表示用户只传递了几组数据进行测试
            if imps_list:
                # 需要对详细内容进行处理，提取imp_name 作为主键，进行分类
                unique_imp = {}
                for imps_dic in imps_list:
                    imp_name = imps_dic["imp_name"]
                    imp_data = imps_dic["imp_data"]
                    imp_pos = imps_dic["imp_pos"]
                    ann_index = imps_dic["annotated_index"]
                    imp_uid = imps_dic["imp_uid"]
                    # 注释改内容
                    # char_limit = imps_dic["char_limit"]
                    unique_imp.setdefault(imp_name, {}).setdefault('imp_data', []).append(imp_data)
                    unique_imp.setdefault(imp_name, {}).setdefault('imp_pos', []).append(imp_pos)
                    # 注释改内容 前端不传char_limit
                    # unique_imp.setdefault(imp_name, {}).setdefault("char_limit", []).append(char_limit)
                    unique_imp.setdefault(imp_name, {}).setdefault("idx", idx)
                    unique_imp.setdefault(imp_name, {}).setdefault("ann_index", []).append(ann_index)
                    unique_imp.setdefault(imp_name, {}).setdefault("imp_uid", []).append(imp_uid)
                unique_imp_lst.append(unique_imp)
        cls[key] = unique_imp_lst
    return cls, classified_groups, json_class_groups


def analy_data(con, o_data):
    cls, classified_groups, json_class_groups = data_merge(con, o_data)
    cls_data = {}
    for key, data in cls.items():
        result = {}
        for item in data:
            for imp_name, value in item.items():
                if imp_name not in result:
                    result[imp_name] = {}
                imp_data = value["imp_data"]
                idx = value["idx"]
                imp_pos = value["imp_pos"]
                ann_index = value["ann_index"]
                imp_uid = value["imp_uid"]
                # 注释限制字符长度
                # char_limit_list = value["char_limit"]
                for i, data in enumerate(imp_data):
                    if i not in result[imp_name]:
                        result[imp_name][i] = {}
                    # result[imp_name][i][data] = {"idx": idx, "pos": imp_pos[i],"char_limit":char_limit_list[i]}
                    result[imp_name][i][data] = {"idx": idx, "pos": imp_pos[i], "ann_index": ann_index[i],
                                                 "imp_uid": imp_uid[i]}
        cls_data[key] = result
    return cls_data, classified_groups, json_class_groups


def analyze_handle(con, o_data):
    """
    :param o_data: 分析数据，对标识的数据信息进行准确的位置信息 ，并给出标识的数据信息中所对应日志信息的下标索引，这样可以避免一些不存在的信息位置
    :return:
    """
    cls_data, classified_groups, json_class_groups = analy_data(con, o_data)

    # 请求体
    project_body = {}
    for key, data in cls_data.items():  # key : method app datatype
        project_body[key] = {}  # key为子模型名称
        # 获取属于当前key 的原始日志信息
        http_data = classified_groups[key]

        for imp_name, value in data.items():  # imp_name :账户、密码
            project_body[key][imp_name] = {}  # {”模型三“:{"账户":{}}}
            for inx, imd_pos in value.items():
                # 给出存储容器信息
                imp_pos = {}
                ht_dic = {}
                # char_limit_list = {}
                ann_index_lst = []
                imp_uid_lst = []

                for imd, idx_pos in imd_pos.items():  # imd 为标识的数据，idx_pos为标识数据所在的位置，索引
                    # 找出数据的索引 信息
                    idx = idx_pos["idx"]
                    pos = idx_pos["pos"]
                    imp_uid = idx_pos["imp_uid"]
                    imp_uid_lst.append(imp_uid)
                    ann_index = idx_pos["ann_index"]
                    ann_index_lst.append(ann_index)
                    # 获取http当前信息
                    http_info = http_data.get(idx)

                    # 添加函数 去除掉imps之后 留下识别的字段信息，请求体跟响应体除外
                    ht_dic, imp_pos = data_search(http_info, imd, imp_pos, ht_dic)

                    # url_dic[imd] = http_info["url"]
                    imp_pos.setdefault(imd, pos)
                    # 注释 后续有需要再开
                    # char_limit_list.setdefault(imd,char_limit)

                project_body[key][imp_name][inx] = {
                    "imp_uid": imp_uid_lst,
                    "imp_pos": imp_pos,
                    # "char_limit_list":char_limit_list
                    "ann_index": list(set(ann_index_lst))
                }
                for h_pos, data in ht_dic.items():
                    project_body.setdefault(key, {}).setdefault(imp_name, {}).setdefault(inx, {}).setdefault(h_pos,
                                                                                                             data)
    return project_body, json_class_groups


def data_search(http_info, imd, imp_pos, ht_dic):
    """
    :param http_info: 源数据信息
    :param imd:  标识数据信息
    :param imp_pos: 数据位置存储
    :param ht_dic: {“request_body”:{}}
    :return:
    """
    for http_key, data in http_info.items():

        if http_key == "imps":
            continue
        else:
            if header_judge(data):
                data = ujson.loads(data)
                data, index_lst = headers_search(data, imd)
                if index_lst:
                    ht_dic.setdefault(http_key, {}).setdefault(imd, data)
                    imp_pos.setdefault(imd, index_lst)
            else:
                index_lst = body_par_search(data, imd)
                if index_lst:
                    ht_dic.setdefault(http_key, {}).setdefault(imd, data)
                    imp_pos.setdefault(imd, index_lst)
    return ht_dic, imp_pos


def header_judge(info):
    """
    :param info: 请求头 响应头 的字符串值
    :return:
    """
    if isinstance(info, str):
        if info.startswith("[{") and info.endswith("}]"):
            return True
    return False


def body_par_search(data, imd):
    """
    对请求体 响应体，参数
    :param data:
    :param imd:
    :return:
    """
    # 需要判断数据是否存在与当前字符串中
    if imd in data:
        # 找到字符串的起始位置
        start_index = data.find(imd)

        # 计算结束位置
        end_index = start_index + len(imd)
        return [start_index, end_index]
    return []


def headers_search(data, imd):
    """对 请求头 响应头"""
    for item in data:
        ii = {}
        if "name" in item:
            key = item["name"]
            value = item["value"]
            res = body_par_search(value, imd)
            if res:
                ii[key] = value
                return ii, res
    return {}, []


def start_end_df_handle(data_source, imp_pos):
    """
    :param data_source: 经过分类的数据源消息 {'13501048148': 'account=13501048148', '13508810307': 'account=13508810307','13503007701': 'account=13503007701'}
    :param imp_pos: 分类消息中标识消息的起始位置和结束位置  {'13501048148': [8, 19], '13508810307': [8, 19], '13503007701': [8, 19]}
    :return:
    continuous_start_df ；起始位置之前相同字符串的索引数组
    continuous_end_df ： 结束位置连续相同字符串的索引数组
    result_df ： 起始位置之前字符串df表
    end_df : 结束位置之后字符串df表
    """

    df = pd.DataFrame.from_dict(data_source, orient='index', columns=['data'])
    df.index.name = 'index'
    # 将 imp_pos1 转换成 DataFrame
    imp_df = pd.DataFrame.from_dict(imp_pos, orient='index', columns=['start_index', 'end_index'])
    imp_df.index.name = 'index'

    # 将 char_limit转化为 DataFrame
    # char_limit_df = pd.DataFrame.from_dict(char_limit_list,orient='index', columns=['char_limit'])
    # char_limit_df.index.name = 'index'
    # 合并两个 DataFrame
    result_df = pd.merge(df, imp_df, left_index=True, right_index=True)
    # result_df = pd.merge(result_df, char_limit_df, left_index=True, right_index=True)
    end_df = result_df.copy()
    # 设置字符提取限制

    # 更新 df - 从起始位置向前提取最多20个字符
    for idx, row in result_df.iterrows():
        # char_limit = row["char_limit"]
        char_limit = 20
        start_index, _ = imp_pos[idx]
        # 判断初始消息
        if start_index > 20:
            ss_index = start_index - 20
        for offset in range(1, min(char_limit, start_index) + 1):
            col_name = str(offset)
            extracted_char = row["data"][start_index - offset] if start_index - offset >= 0 else ""
            result_df.at[idx, col_name] = extracted_char

    # 更新 end_df - 从结束位置向后提取最多20个字符
    for idx, row in end_df.iterrows():
        # char_limit = row["char_limit"]
        char_limit = 20
        _, end_index = imp_pos[idx]
        # 需要确定实际可用的字符数据量
        available_chars = len(row["data"]) - end_index  # 如果大于20 就取20，如果 两个相等 就是0 ，如果小于20就取char_limit
        # 调整提取字符的数量，如果可用字符少于chat_limit,则使用可用字符
        num_chars_to_extract = min(available_chars, char_limit)
        for offset in range(1, num_chars_to_extract + 1):
            col_name = str(offset)
            current_index = end_index - 1 + offset
            extracted_char = row["data"][current_index] if current_index < len(row["data"]) else ""
            end_df.at[idx, col_name] = extracted_char
    # 调用函数返回 连续数组字符串数组
    continuous_start_df = find_continuous_same_columns(result_df, start_chars)
    continuous_end_df = find_continuous_same_columns(end_df, end_chars)
    return continuous_start_df, continuous_end_df, result_df, end_df


def find_continuous_same_columns(df, stop_chars):
    """
    找出连续相同的列，也是经过分析得出的数组，用来之后遍历
    :param df:
    :return:
    """
    continuous_streaks = []
    current_streak = []
    previous_col_number = -1  # Initialize to an invalid column number

    # 循环所有列值，跳过 col='data'的数据
    for col in [col for col in df.columns if
                (col != 'data' and col != 'start_index' and col != 'end_index' and col != 'char_limit')]:
        col_number = int(col)

        # 检查 if当前列所有数据都相同
        if len(df[col].unique()) == 1:
            if previous_col_number == -1 or col_number - previous_col_number == 1:
                current_streak.append(col)
            else:
                # 进行新的连续数据进行比对
                if len(current_streak) > 1:
                    continuous_streaks.append(current_streak)
                current_streak = [col]
        else:

            # 如果当前列 不存在相同的数据，就将之前的存储的数据存储 列表中
            if len(current_streak) > 1:
                continuous_streaks.append(current_streak)
            current_streak = []

        previous_col_number = col_number  # 更新值previous_col_number

    # 检查如果最后队列完成将其添加到列表中
    if len(current_streak) > 1:
        continuous_streaks.append(current_streak)

    if stop_chars:
        continuous_streaks_copy = []
        for streak in continuous_streaks:
            filtered_streaks = []
            # streak 获取到连续字符串的子列表，因为会有从字符串中间取值的问题
            for index in streak:
                if df[index].iloc[0] not in stop_chars:  # 获取当前列是否存在与
                    filtered_streaks.append(index)
                else:
                    filtered_streaks.append(index)
                    break
            continuous_streaks_copy.append(filtered_streaks)
        continuous_streaks = continuous_streaks_copy
    return continuous_streaks


def continuous_df(result_df, end_df, continuous_start_df, continuous_end_df):
    """
    :param result_df: start df表
    :param end_df:   end  df表
    :param continuous_start_df:  起始位置连续索引的数组
    :param continuous_end_df:   结束位置连续索引的数组
    :return: {'start': {'str': '&username=', 's_index': 21},'end': {'str': '&password=', 'e_index': 57}}

    """
    tol_info = {"start": {}, "end": {}}
    # 针对起始字符串
    extracted_start_values = []
    ss_values = []  # 用来找最小起始位置信息
    if continuous_start_df:
        first_lst = continuous_start_df[0]
        for col in first_lst:
            extracted_start_values.append(result_df[col].iloc[0])  # 获取字符串
        # 起始位置 寻找字符串最初位置
        ss_index = first_lst[-1]
        # 需要判断获取的数组中，数组第一位是否为 “1”
        equal_index = first_lst[0]

        # 先将该段注释 （后续如果需要就将其加上）
        # for index, col_data in result_df.iterrows():
        #     idx = col_data["start_index"] - int(ss_index)
        #     ss_values.append(idx)

        tol_info["start"].setdefault("str", "".join(extracted_start_values[::-1]))  # 表示我们的规则字符串

        # 跟上面一段关联
        # tol_info["start"].setdefault("s_index", min(ss_values))  # 表示我们规则字符串的起始位置在哪
        if equal_index != "1":
            tol_info["start"].setdefault("offset_pos", int(equal_index) - 1)  # 直接截取规则字符串后字符串从该下标取到最后

    # 针对 结束字符串
    extracted_end_values = []
    ee_values = []  # 用来找最小结束位置信息
    if continuous_end_df:
        first_lst = continuous_end_df[0]
        for col in first_lst:
            extracted_end_values.append(end_df[col].iloc[0])
        # 结束位置，寻找字符串最初位置
        ee_index = first_lst[-1]
        # 需要判断获取的数组中，数组第一位是否为 “1”
        equal_index = first_lst[0]

        # 将该段注释了因为下标位置在新数据中没什么用 先将该段注释 （后续如果需要就将其加上）
        # for index, col_data in end_df.iterrows():
        #     idx = col_data["end_index"] + int(ee_index)
        #     ee_values.append(idx)
        tol_info["end"].setdefault("str", "".join(extracted_end_values))  # 表示我们的规则字符串

        # 跟上面一段关联
        # tol_info["end"].setdefault("e_index", max(ee_values))  # 表示我们规则字符串的起始位置在哪
        if equal_index != "1":
            tol_info["end"].setdefault("offset_pos", int(equal_index) - 1)  # 直接截取规则字符串后字符串从该下标取到最后
    return tol_info


def rule_info(data_source, imp_pos):
    """
    :param data_source:数据源
    :param imp_pos:
    :param http_pos:
    :return:  根据http日志的位置去进行不同的数据提取
    """

    if all(isinstance(value, str) for value in data_source.values()):
        continuous_start_df, continuous_end_df, result_df, end_df = start_end_df_handle(data_source, imp_pos)
        tol_info = continuous_df(result_df, end_df, continuous_start_df, continuous_end_df)
        # result["default"] = tol_info
        return tol_info

    # elif http_pos == "request_headers" or http_pos == "response_headers":
    elif all(isinstance(value, dict) for value in data_source.values()):
        result = {}
        # 由于 我们获取的key 不知道是
        head_dic = {}
        for imp_name, headers in data_source.items():
            for key, value in headers.items():
                head_dic.setdefault(key, {}).setdefault(imp_name, value)
        for key, data_source in head_dic.items():
            continuous_start_df, continuous_end_df, result_df, end_df = start_end_df_handle(data_source, imp_pos)
            tol_info = continuous_df(result_df, end_df, continuous_start_df, continuous_end_df)
            # 为结果添加key值信息
            result[key] = tol_info

        return result
    else:
        return {}


def handle_project(con, o_data):
    """
    :param o_data: 经过分类之后的数据信息。{key:{"账户":{0:{"request_body":""}}}
    :return:
    """
    project_body, json_class_groups = analyze_handle(con, o_data)

    str_rules = {}
    for model_key, pro_dic in project_body.items():  # project_body: key:{"账户":{0:{"request_body":""}}}

        # imp_name 为用户提供的标识信息，pos_data则是 每个数据索引内标识信息存在的位置及索引位置
        for imp_name, pos_data in pro_dic.items():
            #  pos_data ： {0:{"request_body":}}
            for id, data in pos_data.items():  # id表示http数据的id索引，例如（0，1，2),data :
                imp_pos = data["imp_pos"]  # 从data中获取详情信息
                ann_index = data.get("ann_index", [])  # 获取标识信息的下标
                a_index = ann_index[0]
                imp_uid = data.get("imp_uid")
                # 需要对 data进行循环 这样才能动态的识别字段信息
                str_rules = dynamic_data(data, str_rules, imp_pos, imp_name, a_index, model_key, imp_uid)
    #print(json_class_groups)
    json_rules = fodr_rules(json_class_groups)
    for model_key, model_value in str_rules.items():
        # 获取当前值信息
        j_rules = json_rules.get(model_key, {})
        for name, id_value in model_value.items():
            # 判断字符串模型下面的数据信息
            if name not in j_rules:
                # 如果不存在，就直接添加
                j_rules[name] = {**id_value}  # 创建一个新的字典
            else:
                # 存在 需要将值进行添加
                j_rules[name].update(id_value)

        # 将合并后的值更新回json_rules
        json_rules[model_key] = j_rules
    return json_rules


def dynamic_data(http_data, rules, imp_pos, imp_name, a_index, model_key, imp_uid):
    """
    :param http_data: 请求数据 ，需要动态获取数据信息 并进行识别，判断走那个识别
    :return:
    """
    for key, value in http_data.items():
        if key != "ann_index" and key != "imp_pos" and key != "imp_uid":
            tol_info = rule_info(value, imp_pos)
            if tol_info:
                rules.setdefault(model_key, {}).setdefault(imp_name, {}).setdefault(imp_uid[0] + f"_{str(a_index)}",
                                                                                    {key: tol_info})
    return rules


#                                                   ######保存规则信息######
# 增加规则数据信息
def save_all_data(rules, con, model_key, linfo, file_str):
    """
    保存规则、条件、标签信息到同一个文件中
    :param rules: 规则数据
    :param condition: 条件数据
    :param label_info: 标签信息数据
    :param file_str: 文件名字符串
    :return: 操作结果信息
    """
    # 拼接文件路径
    # base_dir = "/data/xlink/models_paths/"
    base_dir = "../../"
    source_file = os.path.join(base_dir, f"{file_str}_rcl_bak.pkl")
    destination_file = os.path.join(base_dir, f"{file_str}_rcl.pkl")

    # 尝试读取已有的数据
    existing_data = {}
    if os.path.exists(destination_file):
        try:
            with open(destination_file, "rb") as fp:
                existing_data = pickle.load(fp)
        except Exception as e:
            return {"status": "Error", "message": str(e)}
        # 获取现有数据

        # 获取子模型的历史值
        if model_key in existing_data:
            old_model = existing_data.get(model_key, {})
            # 更新现有数据
            old_model["rules"] = rules
            old_model["condition"] = con
            old_model["label_info"] = linfo
        else:
            # 不存在 直接添加
            existing_data[model_key] = {
                "rules": rules,
                "condition": con,
                "label_info": linfo
            }
        # 将更新后的数据写入文件
        try:
            with open(source_file, "wb") as fp:
                pickle.dump(existing_data, fp)

        except OSError as e:
            return {"status": "Error", "message": f"模型存储错误：{str(e)}"}
        # 写入之后 将其移动置我们原文件中，这样做避免出现报错问题
        try:
            os.replace(source_file, destination_file)
            return {"status": "Success", "message": "模型存储成功！"}
        except OSError as e:
            return {"status": "Error", "message": f"模型数据移动出错：{str(e)}"}

    else:
        # 文件不存在
        existing_data[model_key] = {
            "rules": rules,
            "condition": con,
            "label_info": linfo
        }
        res = dump_rules_pkl(existing_data, destination_file)
        return res


def add_all_data(rules, con, model_key, linfo, existing_data):
    """
    保存规则、条件、标签信息到同一个文件中
    :param rules: 规则数据
    :param condition: 条件数据
    :param label_info: 标签信息数据
    :param file_str: 文件名字符串
    :return: 操作结果信息
    """
    # 拼接文件路径
    # base_dir = "/data/xlink/models_paths/"

    # 尝试读取已有的数据
    if existing_data:
        # 获取现有数据
        # 获取子模型的历史值
        # 就是 纯新增
        existing_data[model_key] = {
            "rules": rules,
            "condition": con,
            "label_info": linfo
        }
    else:
        # 数据为空 直接添加
        existing_data[model_key] = {
            "rules": rules,
            "condition": con,
            "label_info": linfo
        }

    return existing_data


#                                                   ######修改规则信息######
def alter_all_data(rules, con, model_key, linfo, old_key, existing_data):
    """
    :param rules: 规则信息
    :param con: con信息
    :param model_key: 修改的新模型名称
    :param linfo:
    :param file_str:
    :param old_key:
    :return:
    """

    datas = {
        "rules": rules,
        "condition": con,
        "label_info": linfo
    }
    # 尝试读取已有的数据
    if existing_data:
        # 需要先找出旧 key的值,将旧的key与新的key进行替换
        if old_key in existing_data:
            existing_data[old_key] = datas  # 让旧的key 的值替换成最新的
            existing_data[model_key] = existing_data.pop(old_key)  # 然后 删除旧的key pop旧key让值等于新key
        else:
            existing_data[model_key] = datas  # 如果旧key不存在 直接新增

    else:
        existing_data[model_key] = datas  # 不存在 直接新增

    return existing_data


def dump_rules_pkl(existing_data, path):
    try:
        with open(path, 'wb') as fp:
            pickle.dump(existing_data, fp)
        return {"status": "Success", "message": "模型存储成功！"}
    except Exception as e:
        return {"status": "Error", "message": str(e)}


#                                                    ######根据结果识别发来的数据结果 ######

def an_data(datass, intell_rules, con):
    """
    :param datass: 标识数据
    :param intell_rules:  形成规则信息
    :param con: 我们的上下文规则信息
    :return:
    """
    # 返回结果JSON对象
    res_data = defaultdict(dict)
    # 对原始数据进行上下文分类处理信息
    for key, condition in con.items():  # 条件查询的名称
        # condition = ujson.loads(condition)  # 将上下文规则转化为字典信息
        for o_data in datass:
            # 获取当前数据信息
            idx = o_data.get("idx")  # 获取当前消息的索引信息
            # 获取HTTP审计日志信息
            http_data = o_data["data"]  #

            # 给出当前需要匹配的详细信息

            if intell_rules:
                res_data = accord_rules(intell_rules, key, http_data, idx, res_data, condition)
            else:
                res_data = {}
    return res_data


def accord_rules(intell_rules, key, http_data, idx, res_data, condition):
    """
    根据获取到的规则进行识别
    :return:
    """
    # 循环condition 的信息
    found = True
    # 循环 只要有一个不符合 那就直接将found设置为False

    found = con_found(condition, http_data, found)
    if found:
        # 判断key是否存在于
        rules_data = intell_rules[key]

        data_storage = {}
        # 循环rules_data 获取到具体的规则
        for ch_name, t_rules in rules_data.items():  # ch_name 标识名称: t_rules {"uuid":{"imp_pos":rules}}
            for uid, rulers in t_rules.items():
                if "JSON" in uid:
                    data_storage = json_identify(data_storage, http_data, rulers, ch_name, uid)
                else:
                    # uid 为改值的唯一标识
                    an_index = uid.split("_")[-1]
                    imp_uid = uid.split("_")[0]
                    for http_pos, pos_rules in rulers.items():
                        current_data = http_data.get(http_pos, "")
                        if header_judge(current_data):
                            data_storage = headers_exract(ch_name, pos_rules, current_data, data_storage, http_pos,
                                                          an_index, imp_uid)
                        else:
                            data_storage = par_body(ch_name, pos_rules, current_data, data_storage, http_pos, an_index,
                                                    imp_uid)

        res_data.setdefault(idx, data_storage)
        #print(res_data)
    return res_data


def con_found(conditions, http_data, found):
    for o_key, con_msg in conditions.items():
        # http_data =o_data["data"]
        val = http_data.get(o_key, "")  # 获取当前键在o里面的值  val相当于我们前台数据信息
        judge = con_msg.get("judge")
        msg = con_msg.get("msg")  # 这相当于 我们在前端界面写的值
        if judge == "=":
            if val != msg:
                found = False  # 表示 该条件不符合 直接跳出该规则
                break
        elif judge == "!=":
            if val == msg:
                found = False
                break
        elif judge == "in":
            if val not in msg:
                found = False
                break
        elif judge == "not in":
            if val in msg:  # 不存在msg中
                found = False
                break
        elif judge == "like":
            if msg not in val:
                found = False
                break
        elif judge == "not like":
            if msg in val:  # 不存在msg中
                found = False
                break
        elif judge == ">":
            if val < msg:
                found = False
                break
        elif judge == "<":
            if val > msg:
                found = False
                break
        elif judge == "<=":
            if val >= msg:
                found = False
                break
        elif judge == ">=":
            if val <= msg:
                found = False
                break
    return found


def par_body(ch_name, pos_rules, data_source, data_storage, pos, an_index, imp_uid):
    """
    处理体部
    :param ch_name:
    :param pos_rules:
    :param data_source:
    :param data_storage:
    :param pos:
    :return:
    """
    # 获取偏移量
    start_offset = pos_rules["start"].get("offset_pos", 0)
    end_offset = pos_rules["end"].get("offset_pos", 0)
    # pos_rules 为 {start:{},end:{}}
    start_str = pos_rules["start"].get("str", "")
    end_str = pos_rules["end"].get("str", "")
    # 根据两者信息 从数据中提取出重要信息
    start_pos, end_pos = s_e_str(start_str, end_str, data_source)

    if start_pos != -1 and end_pos != -1:
        current_start = start_pos + start_offset
        current_end = end_pos - end_offset
        res = data_source[current_start:current_end].strip()

        if res != "":
            for end in end_chars:
                if end in res:
                    res = res[:res.index(end)]
            # data_storage.setdefault(an_index, {}).setdefault(pos, {}).setdefault(ch_name, res)
            data_storage.setdefault(imp_uid, {}).setdefault("identifyResults", []).append(res)
    return data_storage


def headers_exract(ch_name, pos_rules, current_data, data_storage, pos, an_index, imp_uid):
    """
    处理头部的识别信息
    :param ch_name:
    :param pos_rules:
    :param request_headers:
    :param data_storage:
    :param pos:
    :return:
    """
    try:
        current_data = ujson.loads(current_data)
    except:
        current_data = []
    for key, rule in pos_rules.items():
        for item in current_data:
            if item["name"].lower() == key.lower():
                start_rule = rule["start"]
                end_rule = rule["end"]
                # 获取偏移量

                start_offset = start_rule.get("offset_pos", 0)
                start_str = start_rule.get("str", "")

                end_offset = end_rule.get("offset_pos", 0)
                end_str = end_rule.get("str", "")
                # 如果相等，就开始让规则从该数据中取出重要信息
                # 如果存在空值怎么办
                # 根据两者信息 从数据中提取出重要信息
                values = item.get("value", "")
                if values:  # 如果存在该值则进行查找
                    start_pos, end_pos = s_e_str(start_str, end_str, values)
                    # 如果找到了起始字符串和结束字符串
                    if start_pos != -1 and end_pos != -1:
                        current_start = start_pos + start_offset
                        current_end = end_pos - end_offset
                        res = item["value"][current_start:current_end].strip()

                        if res != "":
                            for end in end_chars:
                                if end in res:
                                    res = res[:res.index(end)]
                            data_storage.setdefault(imp_uid, {}).setdefault("identifyResults", []).append(res)
                            # data_storage.setdefault(imp_uid, {}).setdefault("fewLogs",an_index)
                            # data_storage.append({imp_uid,{}}.setdefault("identifyResults",[]).append(res).setdefault("fewLogs", an_index))
                            # data_storage.setdefault(an_index, {}).setdefault(pos, {}).setdefault(ch_name, res)
                            break
                else:
                    continue
    return data_storage


def s_e_str(start_str, end_str, data_source):
    """
    根据起始字符串 结束字符串 数据 获取到当前识别信息
    :param start_str:
    :param end_str:
    :param data_source:
    :return:
    """
    if start_str and end_str:
        start_pos = data_source.find(start_str)
        if start_pos != -1:
            start_pos += len(start_str)  # 从获取到起始的最后面 再去寻找结束字符串
            end_pos = data_source.find(end_str, start_pos)
        else:
            start_pos = -1
            end_pos = -1

    elif start_str:
        # 如果 start_pos存在
        start_pos = data_source.find(start_str)
        if start_pos != -1:
            # 证明存在 该字符串
            start_pos += len(start_str)
            end_pos = len(data_source)
        else:
            start_pos = -1
            end_pos = -1
    elif end_str:
        # 如果只有结尾字符串
        start_pos = 0
        end_pos = data_source.find(end_str, start_pos)
    else:
        start_pos = 0
        end_pos = len(data_source)
    return start_pos, end_pos


#                                                       ######配置信息代码######

def x_uuids(x):
    return str(time.perf_counter())


#                                           ######模型名称判断代码######
def found_path(path_name):
    """判断字符串是否存在了"""
    x_p = "/data/xlink/x_t_p.pkl"

    if os.path.exists(x_p):
        with open(x_p, 'rb') as fp:
            n_lst = pickle.load(fp)  # 模型名称列表
        if path_name not in n_lst:
            n_lst.append(path_name)
            return {"status": "Success", "msg": f"模型名-{path_name}-创建成功！"}
        else:
            return {"status": "Error", "msg": f"模型名-{path_name}-已经存在！"}
    else:
        # 不存在 x_p_bak这个文件，
        path_lst = [path_name]
        with open(x_p, "wb") as fp:
            pickle.dump(path_lst, fp)
        return {"status": "Success", "msg": f"模型名-{path_name}-创建成功！"}


#                                           ######读取模型文件并识别结果######
def read_model_identify(models_data, o):
    data_storage = {}
    label_info = {}
    label_dic = {}
    if models_data:
        for model_key, data in models_data.items():  # model_key :测试7 ,{}
            # 第一条信息
            # print(data)
            # 先进行筛选条件的判断
            conditions = data.get("condition", {})
            rulers = data.get("rules", {})
            l_info = data.get("label_info", {})

            # 身处 同一 子模型名称下面，需要判断上下文规则是否满足，如果满足则进行规则识别
            try:
                found = con_judge(conditions, o)
            except Exception as e:
                return f"上下文规则数据出错：{e.__str__()}"

            if found:
                # 如果上下文规则成立，那就对规则进行读取
                try:
                    data_storage = rule_judge(rulers, o, data_storage)
                except Exception as e:
                    return f"模型识别数据出错：{e.__str__()}"
                # 返回识别数据与标签信息
                # if data_storage:
                #     return {"status": "Success", "msg": "模型识别成功！", "data": data_storage, "label_info": l_info}
                # else:
                #     return {"label_info": l_info}
                for label, value in l_info.items():
                    if value != "" and value not in label_info.setdefault(label, []):
                        label_info[label].append(value)
            else:
                continue
        for label, val_lst in label_info.items():
            if len(val_lst) >= 1:
                label_dic[label] = val_lst[0]
        if data_storage or label_dic:
            return {"status": "Success", "msg": "模型识别成功！", "data": data_storage, "label_info": label_dic}
        else:
            return {}
    return {}


def con_judge(condition, o):
    """
    :param condition: 上下文规则条件
    :param o: 数据源
    :return:
    """

    found = True
    found = con_found(condition, o, found)
    return found


def rule_judge(rulers, o, data_storage):
    """
    对规则进行识别
    """
    # ch_name中包含着数据信息 返回 操作
    for ch_name, ch_data in rulers.items():
        for uid, imp_data in ch_data.items():
            if "JSON" in uid:
                data_storage = model_data_extract(ch_name, o, data_storage, imp_data)
            else:
                for http_pos, rle in imp_data.items():
                    current_data = o.get(http_pos, "")
                    if header_judge(current_data):

                        data_storage = headers_models(current_data, rle, http_pos, ch_name, data_storage)

                    elif isinstance(current_data, list):
                        data_storage = headers_models(current_data, rle, http_pos, ch_name, data_storage)
                    else:
                        data_storage = body_models(current_data, rle, http_pos, ch_name, data_storage)

    return data_storage


def headers_models(current_data, pos_rules, http_pos, ch_name, data_storage):
    try:
        current_data = ujson.loads(current_data)
    except:
        current_data = current_data
    for key, rule in pos_rules.items():
        for item in current_data:
            if item["name"].lower() == key.lower():
                start_rule = rule["start"]
                end_rule = rule["end"]
                # 获取偏移量

                start_offset = start_rule.get("offset_pos", 0)
                start_str = start_rule.get("str", "")

                end_offset = end_rule.get("offset_pos", 0)
                end_str = end_rule.get("str", "")
                # 如果相等，就开始让规则从该数据中取出重要信息
                # 如果存在空值怎么办

                # 根据两者信息 从数据中提取出重要信息
                values = item.get("value", "")
                if values:  # 如果存在该值则进行查找
                    start_pos, end_pos = s_e_str(start_str, end_str, values)
                    # 如果找到了起始字符串和结束字符串
                    if start_pos != -1 and end_pos != -1:
                        current_start = start_pos + start_offset
                        current_end = end_pos - end_offset
                        res = item["value"][current_start:current_end].strip()
                        ch_name_lst = ch_name.split(">>")  # 取0索引，但是我还是要判断一下>>存不存在，如果不想存在，就直接返回当前字符串了
                        if len(ch_name_lst) > 1:
                            ch_name = ch_name_lst[1]
                            type_name = ch_name_lst[0]
                        else:
                            type_name = ""

                        if res != "" and res not in data_storage.setdefault(http_pos, {}).setdefault(type_name,
                                                                                                     {}).setdefault(
                            ch_name, []):
                            for end in end_chars:
                                if end in res:
                                    res = res[:res.index(end)]
                            data_storage[http_pos][type_name][ch_name].append(res)
                else:
                    continue
    return data_storage


def body_models(data_source, pos_rules, http_pos, ch_name, data_storage):
    """
    处理体部
    :param ch_name:
    :param pos_rules:
    :param data_source:
    :param data_storage:
    :param pos:
    :return:
    """
    # 获取偏移量
    start_offset = pos_rules["start"].get("offset_pos", 0)
    end_offset = pos_rules["end"].get("offset_pos", 0)
    # pos_rules 为 {start:{},end:{}}
    start_str = pos_rules["start"].get("str", "")
    end_str = pos_rules["end"].get("str", "")
    # 根据两者信息 从数据中提取出重要信息
    start_pos, end_pos = s_e_str(start_str, end_str, data_source)

    if start_pos != -1 and end_pos != -1:
        current_start = start_pos + start_offset
        current_end = end_pos - end_offset
        res = data_source[current_start:current_end].strip()
        # 根据空值会有搜索为空的信息，所以这里空值也进行存储
        # 对 ch_name 进行分割
        ch_name_lst = ch_name.split(">>")  # 取0索引，但是我还是要判断一下>>存不存在，如果不想存在，就直接返回当前字符串了
        if len(ch_name_lst) > 1:
            ch_name = ch_name_lst[1]
            type_name = ch_name_lst[0]
        else:
            type_name = ""
        if res != "" and res not in data_storage.setdefault(http_pos, {}).setdefault(type_name, {}).setdefault(ch_name,
                                                                                                               []):
            for end in end_chars:
                if end in res:
                    res = res[:res.index(end)]
            data_storage[http_pos][type_name][ch_name].append(res)

    return data_storage


#                   ##########删除子模型数据##########
def delete_rules_data(model_key, file_str):
    # 拼接文件路径
    base_dir = "/data/xlink/models_paths/"
    # base_dir = "./"
    source_file = os.path.join(base_dir, f"{file_str}_rcl_bak.pkl")
    destination_file = os.path.join(base_dir, f"{file_str}_rcl.pkl")
    try:
        with open(destination_file, "rb") as fp:
            tol_rulers = pickle.load(fp)
    except Exception as e:
        return {"status": "Error", "msg": f"模型数据读取错误：{e.__str__()}"}

    # 删除模型名称
    new_tol_rulers = {}
    if model_key in tol_rulers:
        try:
            del tol_rulers[model_key]
            # 将模型数据写入副本文件 中

            res = write_replace(source_file, destination_file, tol_rulers)
            if res.get("status") == "Success":
                return {"status": "Success", "msg": f"子模型-{model_key}-删除成功！"}
            else:
                return res
        except:
            try:
                # 循环 tol_rules 数据，
                for current_key, data in tol_rulers.items():
                    if current_key != model_key:
                        new_tol_rulers[current_key] = data
                res = write_replace(source_file, destination_file, new_tol_rulers)
                if res.get("status") == "Success":
                    return {"status": "Success", "msg": f"子模型-{model_key}-删除成功！"}
                else:
                    return res
            except:
                return {"status": "Error", "msg": f"子模型-{model_key}-删除错误"}

    else:
        return {"status": "Error", "msg": f"子模型-{model_key}-模型数据不存在！"}


def write_replace(source_file, destination_file, tol_rulers):
    # 将模型数据写入副本文件 中
    try:
        with open(source_file, "wb") as fp:
            pickle.dump(tol_rulers, fp)
    except OSError as e:
        return {"status": "Error", "message": f"模型存储错误：{str(e)}"}
    # 写入之后 将其移动置我们原文件中，这样做避免出现报错问题
    try:
        os.replace(source_file, destination_file)
        return {"status": "Success", "message": "模型存储成功！"}
    except OSError as e:
        return {"status": "Error", "message": f"模型数据移动出错：{str(e)}"}


def load_data(destination_file):
    # 拼接文件路径
    # base_dir = "/data/xlink/models_paths/"
    if os.path.exists(destination_file):
        with open(destination_file, "rb") as fp:
            return pickle.load(fp)
    return {}


def load_model_data(file_str):
    # 需要放入xlink中进行判断，拼接字符串
    base_dir = "/data/xlink/models_paths/"

    source_file = os.path.join(base_dir, f"{file_str}_rcl.pkl")
    if os.path.exists(source_file):
        with open(source_file, "rb") as fp:
            return pickle.load(fp)
    return {}


#                                 #########add rzc 2024/4/28 ##############
def up_file_model(upload_file, file_str, base_dir):
    """
    :param new_file: 上传的文件
    :param file_str: 当前界面模型文件名称
    :return:
    """
    source_file = os.path.join(base_dir, f"{file_str}_rcl_bak1.pkl")
    old_model_file = os.path.join(base_dir, f"{file_str}_rcl.pkl")
    if os.path.exists(old_model_file):
        try:
            with open(upload_file, "rb") as fp:
                loaded_data = pickle.load(fp)

        except pickle.UnpicklingError as e:
            return {"status": "Error", "message": f"模型文件格式错误：{e.__str__()}"}

        # 现在需要读取最新文件信息
        try:
            with open(old_model_file, "rb") as fp:
                old_data = pickle.load(fp)
        except Exception as e:
            return {"status": "Error", "message": f"读取当前模型失败：{e.__str__()}"}

        # 需要将两个文件合并到一起，如果模型名称相同怎么办,分为 覆盖，保留原始值，或者合并，将三种情况全部写出来吧
        # ① 保留当前模型的值，祛除导入模型的值
        try:
            for current_key, current_value in loaded_data.items():
                if current_key not in old_data:
                    old_data[current_key] = current_value
        except Exception as e:
            return {"status": "Error", "message": f"模型覆盖错误：{e.__str__()}"}
        res = write_replace(source_file, old_model_file, old_data)
        # ② 覆盖原值,将导入的值作为新值覆盖掉旧值
        # old_data.update(loaded_data)

        # ③ 合并模型，保留两个模型中相同的key，将两个模型中不同的key合并到一起，这个是将模型转化为列表存储了
        return res
    else:
        try:
            os.replace(upload_file, old_model_file)
            return {"status": "Success", "message": "模型存储成功！"}
        except OSError as e:
            return {"status": "Error", "message": f"模型数据移动出错{str(e)}"}


#                ################处理json格式的数据信息###############
def fodr_rules(json_class_groups):
    """
    :param classified_groups:{
                    "key":[
                        {
                            "data":{"request_body":"","response_body":""},
                            "imps":[{},{}]
                        },
                        {
                        "data":{"request_body":"","response_body":""},
                            "imps":[{},{}]
                        }
                          ],
                    }
    key:标识上下文相同数据信息
    data:表示日志信息
    imps:表示人工标识数据信息
    :return:
    """
    # condition就是我们的上下文规则 {“美创”:""}
    # classified_groups, json_class_groups = classify_data1(condition, datas)
    rules = {}

    for key, data_imps in json_class_groups.items():
        rules[key] = {}
        for idx, id_dic in data_imps.items():
            # 一个key值存在多个键值，就比如在一条消息内我们要标识说多种信息 所以data_imps是列表
            imps_list = id_dic["imps"]
            # 这里要获取 位置信息 存在的位置 目前只有两个 json情况下 只有有两个分析他的位置信息

            set_imp = list(set([imps["imp_pos"] for imps in imps_list]))
            for http_pos, h_data in id_dic.items():
                if http_pos == "imps":
                    # 获取单条数据信息及标识信息
                    continue
                else:
                    # http_pos是位置信息,字符串信息数据
                    pos_data = h_data
                    if http_pos in set_imp:
                        try:
                            pos_data = ujson.loads(pos_data)
                        except:
                            pos_data = pos_data
                    if pos_data:
                        rules = cification(key, pos_data, imps_list, rules)

    return rules


def cification(key, data_soure, imps, rules):
    for imp in imps:
        # 对每个记录找到的路径都进行单独的查找和记录,这个不做对比
        imp_data = imp["imp_data"]
        imp_pos = imp["imp_pos"]
        imp_name = imp["imp_name"]
        imp_type = imp["imp_type"]
        imp_uid = imp["imp_uid"]
        a_index = imp["annotated_index"]
        target = preprocess_target(imp_data)
        # 进行递归查找，这个是做了全局的查找了

        paths_dict = find_values_in_dict_little(data_soure, target, imp_pos, imp_type)

        for target, paths in paths_dict.items():

            if paths:
                #rules[key].setdefault()
                rules[key].setdefault(imp_name, {}).setdefault("JSON" + imp_uid + f"_{str(a_index)}", {}).setdefault(
                    imp_pos,
                    []).extend(
                    list(set(paths)))
    return rules


def find_values_in_dict_little(data, target, imp_pos, imp_type, path='', found_paths=None):
    if found_paths is None:
        found_paths = {str(target): []}

    if isinstance(data, dict):
        # 判断递归的data是否等于target
        if data == target:
            found_paths[str(target)].append(path)
        for key, value in data.items():
            current_path = f'{path}.{key}' if path else key

            if value == target or str(key) == str(target):
                found_paths[str(target)].append(current_path)

            if isinstance(value, str) and is_json_string(value):
                try:
                    json_value = ujson.loads(value)
                    if json_value == target:
                        found_paths[str(target)].append(current_path + "-JSON")
                    find_values_in_dict_little(json_value, target, imp_pos, imp_type, current_path + "-JSON",
                                               found_paths)
                except ValueError:
                    pass
            elif isinstance(value, (dict, list)):
                find_values_in_dict_little(value, target, imp_pos, imp_type, current_path, found_paths)
    elif isinstance(data, list):
        if data == target:
            found_paths[str(target)].append(path)
        for index, item in enumerate(data):
            if imp_type != "JSON":
                current_path = f"{path}-LIST"
            else:
                # current_path = f"{path}-[{index}]"
                current_path = f"{path}-[0]"
            find_values_in_dict_little(item, target, imp_pos, imp_type, current_path, found_paths)

    return found_paths


def is_json_string(s):
    return (s.strip().startswith('{') and s.strip().endswith('}')) or (
            s.strip().startswith('[') and s.strip().endswith(']'))


def preprocess_target(target):
    if isinstance(target, str) and is_json_string(target):
        try:
            # 尝试将JSON字符串的target解析为字典
            preprocess = ujson.loads(target)
        except:
            preprocess = target
    else:
        preprocess = target
    return preprocess


# 对json数据进行识别
def json_identify(data_storage, http_data, rule, ch_name, uid):
    """
    :param rules: 生成的规则信息
    :param data_tol: 需要进行识别的数据信息
    :param condition: 上下文条件
    :return: 返回识别的结果信息
    """
    # 获取规则中的key值
    imp_uuid = uid.split("_")[1]
    imp_uid = uid.split("_")[0].replace("JSON","")
    for http_pos, r_lst in rule.items():

        # 在前端调用的时候保存的是单个上下文规则
        # 获取相应的规则信息
        data_source = http_data.get(http_pos, "")
        if data_source:
            # 循环 req_rule 获取请求体中的响应数据
            # request_body = ujson.loads(request_body)
            for t_rule in r_lst:  # t_rule {"发票物品":[]}
                # ch_name:发票物品，rls:['bwxx-JSON.dataMap.dzfpKpywFpmxxxbVOList-[0].xmmc']
                value_lst = []
                # 'bwxx-JSON.dataMap.dzfpKpywFpmxxxbVOList-[0].xmmc'
                value_lst = get_value_by_path(data_source, t_rule, value_lst)
                if value_lst:
                    data_storage.setdefault(imp_uid, {}).setdefault("identifyResults", []).append(value_lst[0])
                    #data_storage.setdefault(imp_uuid, {}).setdefault(http_pos, {}).setdefault(ch_name, value_lst[0])

    return data_storage


def get_value_by_path1(data_source, path, value_lst):
    """
    最老版本 嵌套不能用
    :param data_source:
    :param path:
    :param value_lst:
    :return:
    """
    # 先将请求响应体进行转化为dict对象
    try:
        current = ujson.loads(data_source)

    except:
        current = data_source

    # 从给定的数据中进行识别
    if isinstance(current, dict):
        temp_current = current
        found = True
        path_list = path.split(".")
        for p in path_list:
            # 循环当前path 每段路径，先判断JSON数据
            if p.endswith("-JSON"):
                key = p.split("-")[0]
                temp_current = temp_current.get(key)
                if not current:
                    found = False
                    break
                temp_current = ujson.loads(temp_current)
            # 判断是否为列表数据
            elif "-[" in p:
                key, index = p.split("-[")
                key = key.strip()
                index = int(index[:-1])
                temp_current = temp_current.get(key, [])  # 获取到该key值 下面的列表
                if not temp_current or index >= len(temp_current):
                    found = False
                    break
                # 已经判断是列表，进行循环查询数据

                # temp_current = temp_current[index]
                # 新增代码 判断循环列表数据
                if isinstance(temp_current, list) and path_list.index(p) < len(path_list) - 1 and (
                        "-[" not in path_list[
                    path_list.index(p) + 1]):
                    for item in temp_current:
                        value = item.get(path_list[path_list.index(p) + 1])
                        if value:
                            found = True
                            value_lst.append(value)
                temp_current = temp_current[index]
            else:

                temp_current = temp_current.get(p)
            if not temp_current:
                found = False
                break
        if found and not isinstance(temp_current, list):
            if temp_current not in value_lst:
                value_lst.append(temp_current)
            return value_lst
    return []


def get_value_by_path2(data_source, path, value_lst):
    """
    最新修改完列表值获取的操作
    :param data_source:
    :param path:
    :param value_lst:
    :return:
    """
    try:
        current = ujson.loads(data_source) if isinstance(data_source, str) else data_source
    except:
        current = data_source
    # 加一个条件当前路径在列表中的索引,用作最后的值判断啊
    idx_in_lst = 0  # 默认为0
    if isinstance(current, dict):
        temp_current = current
        found = True
        path_list = path.split(".")
        for index, p in enumerate(path_list):
            if p.endswith("-JSON"):
                key = p.split("-")[0]
                temp_current = temp_current.get(key)
                idx_in_lst = index
                if not temp_current:
                    found = False
                    break
                temp_current = ujson.loads(temp_current)
            elif "-LIST" in p:
                key, _ = p.split("-LIST")
                key = key.strip()

                temp_current = temp_current.get(key, [])  # 循环到这里就是一个列表信息
                idx_in_lst = index
                if not temp_current:
                    found = False
                    break
                if p != path_list[-1]:  # 如果路径还未结束，则需要继续处理列表中的元素

                    for item in temp_current:  # 循环该列表信息
                        value_lst = get_value_by_path(item, ".".join(path_list[index + 1:]), value_lst)
                    break
                # 不再需要这个else，因为已经在循环中添加了列表中的每个元素
            else:
                temp_current = temp_current.get(p)
                idx_in_lst = index
            if not temp_current:
                found = False
                break

        # if found and not isinstance(temp_current, list):
        # 判断 当前值不为列表值，如果是列表值则当前的路径必须是最后段
        if found and ((not isinstance(temp_current, list)) or (
                (isinstance(temp_current, list)) and idx_in_lst == len(path_list) - 1)):
            if temp_current not in value_lst:
                value_lst.append(temp_current)

    return value_lst


def get_value_by_path3(data_source, path, value_lst):
    """
    最新修改完列表值上添加索引操作
    :param data_source:
    :param path:
    :param value_lst:
    :return:
    """
    try:
        current = ujson.loads(data_source) if isinstance(data_source, str) else data_source
    except:
        current = data_source
    # 加一个条件当前路径在列表中的索引,用作最后的值判断啊
    idx_in_lst = 0  # 默认为0
    if isinstance(current, dict):
        temp_current = current
        found = True
        path_list = path.split(".")
        for index, p in enumerate(path_list):
            if p.endswith("-JSON"):
                key = p.split("-")[0]
                temp_current = temp_current.get(key)
                idx_in_lst = index
                if not temp_current:
                    found = False
                    break
                temp_current = ujson.loads(temp_current)
            elif "-LIST" in p:
                key, _ = p.split("-LIST")
                key = key.strip()

                temp_current = temp_current.get(key, [])  # 循环到这里就是一个列表信息
                idx_in_lst = index
                if not temp_current:
                    found = False
                    break
                if p != path_list[-1]:  # 如果路径还未结束，则需要继续处理列表中的元素

                    for item in temp_current:  # 循环该列表信息
                        value_lst = get_value_by_path(item, ".".join(path_list[index + 1:]), value_lst)
                    break
                # 不再需要这个else，因为已经在循环中添加了列表中的每个元素
            elif "-[" in p and p.endswith("]"):
                key, index = p.split("-[")
                key = key.strip()
                index = int(index[:-1])
                temp_current = temp_current.get(key, [])
                if not temp_current or index >= len(temp_current):
                    found = False
                    break
                temp_current = temp_current[index]
            else:
                temp_current = temp_current.get(p)
                idx_in_lst = index
            if not temp_current:
                found = False
                break

        # if found and not isinstance(temp_current, list):
        # 判断 当前值不为列表值，如果是列表值则当前的路径必须是最后段
        if found and ((not isinstance(temp_current, list)) or (
                (isinstance(temp_current, list)) and idx_in_lst == len(path_list) - 1)):
            if temp_current not in value_lst:
                value_lst.append(temp_current)

    return value_lst


def get_value_by_path(data_source, path, value_lst):
    """
    根据给定路径获取数据源中的值并添加到value_lst中
    :param data_source: 数据源，可以是JSON字符串、字典或列表
    :param path: 访问路径，使用"."分隔
    :param value_lst: 存储结果值的列表
    :return: value_lst
    """
    try:
        current = ujson.loads(data_source) if isinstance(data_source, str) else data_source
    except Exception as e:
        print(f"Error loading JSON: {e}")
        return value_lst

    path_list = path.split(".")

    idx_in_lst = 0  # 当前路径在列表中的索引，用于最后的值判断

    def traverse_path(temp_current, path_list, value_lst, idx_in_lst):
        found = True
        for index, p in enumerate(path_list):
            if p.endswith("-JSON"):
                key = p.split("-")[0]
                temp_current = temp_current.get(key)
                idx_in_lst = index
                if not temp_current:
                    found = False
                    break
                try:
                    temp_current = ujson.loads(temp_current)
                except Exception as e:
                    print(f"Error loading JSON from key '{key}': {e}")
                    found = False
                    break

            elif "-LIST" in p:
                key, _ = p.split("-LIST")
                key = key.strip()
                temp_current = temp_current.get(key, [])
                idx_in_lst = index
                if not temp_current:
                    found = False
                    break
                if p != path_list[-1]:  # 如果路径还未结束，则需要继续处理列表中的元素
                    for item in temp_current:
                        value_lst = traverse_path(item, path_list[index + 1:], value_lst, idx_in_lst)
                    break
            elif "-[" in p and p.endswith("]"):
                key, index = p.split("-[")
                key = key.strip()
                try:
                    index = int(index[:-1])
                except ValueError:
                    print(f"Invalid index in path: {p}")
                    found = False
                    break
                temp_current = temp_current.get(key, [])
                if not temp_current or index >= len(temp_current):
                    found = False
                    break
                temp_current = temp_current[index]

            else:
                temp_current = temp_current.get(p)
                idx_in_lst = index
            if not temp_current:
                found = False
                break

        if found and ((not isinstance(temp_current, list)) or (
                isinstance(temp_current, list) and idx_in_lst == len(path_list) - 1)):
            if temp_current not in value_lst:
                value_lst.append(temp_current)
        return value_lst

    # 如果数据源是列表，遍历每个元素
    if isinstance(current, list):
        # 如果刚开始就是list 那么第一个path  不是 -LIST 就是 -[0]

        if path_list[0] == "-LIST":
            # 如果是第一个
            for item in current:
                value_lst = traverse_path(item, path_list[1:], value_lst, idx_in_lst)
        else:
            item = current[0]
            value_lst = traverse_path(item, path_list[1:], value_lst, idx_in_lst)
    else:
        value_lst = traverse_path(current, path_list, value_lst, idx_in_lst)

    return value_lst


def model_data_extract(ch_name, o, data_storage, imp_data):
    """
    用于xlink中处理
    :param ch_name:
    :param o:
    :param ch_data:
    :param data_storage:
    :return:
    """

    for http_pos, rle_lst in imp_data.items():
        current_data = o.get(http_pos, "")
        if current_data:
            for t_rule in rle_lst:
                value_lst = []
                value_lst = get_value_by_path(current_data, t_rule, value_lst)
                # 对 ch_name 进行分割
                ch_name_lst = ch_name.split(">>")  # 取0索引，但是我还是要判断一下>>存不存在，如果不想存在，就直接返回当前字符串了
                if len(ch_name_lst) > 1:
                    ch_name = ch_name_lst[1]
                    type_name = ch_name_lst[0]
                else:
                    type_name = ""
                if value_lst:
                    data_storage.setdefault(http_pos, {}).setdefault(type_name, {}).setdefault(ch_name, []).extend(
                        value_lst)

    return data_storage


# add rzc on 2024/7/17 针对子模型标签信息进行判断
def label_judge(model_data,label_key,label_name):
    model_file_data = {}
    for model_key,rule_data in model_data.items():
        label_info = rule_data.get("label_info",{})
        if label_info.get(label_key) == label_name:
            model_file_data[model_key] = rule_data
    return model_file_data

def merge_dicts(d1, d2):
    for key in d2:
        if key in d1:
            if isinstance(d1[key], dict) and isinstance(d2[key], dict):
                merge_dicts(d1[key], d2[key])
            elif isinstance(d1[key], list) and isinstance(d2[key], list):
                # 将d2[key]的内容追加到d1[key]，并去重
                d1[key] = list(set(d1[key] + d2[key]))
            elif isinstance(d1[key], int) and isinstance(d2[key], int):
                # 如果是整数，则相加
                d1[key] += d2[key]
            else:
                d1[key] = d2[key]
        else:
            d1[key] = d2[key]
    return d1


def intell_sen1(model_file_data, monitor):
    key_ch = {"response_body": "响应体", "request_body": "请求体", "parameter": "参数"}
    total_info = {}
    total_count = {}
    info = {}
    level_lst = []
    cls_lst = []
    count = {}
    max_level=0
    # sen_level = {"1":"L1","2":"L2","3":"L3","4":"L4"}
    sen_level = {"L1": 1, "L2": 2, "L3": 3, "L4": 4}
    analy_data = read_model_identify(model_file_data,monitor)
    if isinstance(analy_data,dict):
        imp_data = analy_data.get("data")
        if imp_data:
            for pos, rule_data in imp_data.items():
                ch_pos = key_ch.get(pos, pos)
                sens = {}
                for cls_level, sen_data in rule_data.items():
                    cls, level_ch = cls_level.split("-")
                    level_lst.append(int(sen_level.get(level_ch)))
                    cls_lst.append(cls)
                    for k, v in sen_data.items():
                        sens.setdefault(k,[]).extend(v)
                        total_info.setdefault(ch_pos, {}).setdefault(cls, {}).setdefault(level_ch, {}).setdefault(k,
                                                                                                                  list(set(v)))
                        total_count.setdefault(ch_pos, {}).setdefault(cls, {}).setdefault(level_ch, {}).setdefault(k, len(list(
                            set(v))))
                        info.setdefault(ch_pos, {}).setdefault(cls, {}).setdefault(level_ch, {}).setdefault(k, {
                            "数量": len(list(set(v))), "内容": list(set(v))})
                count.setdefault(ch_pos,{k: len(list(set(v))) for k, v in sens.items()})

            if level_lst:
                max_level = max(level_lst)
            else:
                max_level = 0
            cls_lst = list(set(cls_lst))
    return total_info, total_count, max_level, info, cls_lst,count
if __name__ == '__main__':
    model_data = {

        "地址解析": {'rules': {'地址信息-L1>>详细地址': {'JSON1118690.892120725_0': {'response_body': ['result.addressComponent.address']}}, '地址信息-L1>>城市': {'JSON1118690.89217796_1': {'response_body': ['result.addressComponent.city']}}, '地址信息-L1>>国家': {'JSON1118690.892217229_2': {'response_body': ['result.addressComponent.nation']}}, '地址信息-L1>>城区': {'JSON1118690.892250598_3': {'response_body': ['result.addressComponent.county']}}, '省份': {'JSON1118690.892289247_4': {'response_body': ['result.addressComponent.province']}}}, 'condition': {'app': {'judge': '=', 'msg': '100.12.66.55'}, 'url': {'judge': '=', 'msg': 'http://100.12.66.55/api/geocoder'}}, 'label_info': {'日志类型': '敏感监测'}},
        "测试1": {'rules': {'登录令牌>>令牌': {'1026762.157071206_0': {'request_headers': {'Authorization': {'start': {}, 'end': {}}}}}}, 'condition': {'app': {'judge': 'in', 'msg': ['192.168.229.156', '192.168.23.202']}}, 'label_info': {'name': '测试', '日志类型': '业务访问'}},
        "账号登录": {'rules': {'返回结果>>账户': {'1027799.015130446_0': {'request_body': {'start': {'str': '&username='}, 'end': {'str': '&'}}}}, '操作>>密码': {'1027799.082829513_1': {'request_body': {'start': {'str': '&password='}, 'end': {'str': '&'}}}}, '返回结果>>会话ID': {'1027799.10287347_2': {'request_headers': {'Cookie': {'start': {'str': 'JSESSIONID='}, 'end': {}}}}}}, 'condition': {'app': {'judge': '=', 'msg': '41.204.84.91:9090'}, 'urld': {'judge': '=', 'msg': 'http://41.204.84.91:9090/login.jsp'}}, 'label_info': {'name': '', '日志类型': '业务访问'}}
    }
    label_key = "日志类型"
    label_name = "敏感监测"
    model_file_data = label_judge(model_data, label_key, label_name)
    print(model_file_data)