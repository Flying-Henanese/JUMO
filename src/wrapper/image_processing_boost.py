import copy
from os import cpu_count
import numpy as np
from utils.workers_threading_pool import ThreadPoolSingleton
from mineru.utils.ocr_utils import OcrConfidence, calculate_is_angle,get_rotate_crop_image

CONCURRENCY = min(cpu_count()//2, 16)
def get_ocr_result_list_parallel(ocr_res, useful_list, ocr_enable, new_image, lang, max_workers=8) ->list:
    ori_im = new_image.copy()
    # 按 batch_size 划分参数列表
    params = []
    batch_size = max(1, len(ocr_res) // CONCURRENCY)
    for i in range(0, len(ocr_res), batch_size):
        batch_ocr = ocr_res[i:i+batch_size]
        params.append((batch_ocr, useful_list, ocr_enable, ori_im, lang))
    results = []
    futures = [ThreadPoolSingleton().submit(process_batch, *arg) for arg in params]
    for fut in futures:
        res = fut.result()
        if res:
            results.extend(res)
    return results

def process_batch(batch_ocr, useful_list, ocr_enable, ori_im, lang)->list[dict]:
    res_list = []
    for box_ocr_res in batch_ocr:
        res = process_box(box_ocr_res, useful_list, ocr_enable, ori_im, lang)
        if res:
            res_list.append(res)
    return res_list

def process_box(box_ocr_res, useful_list, ocr_enable, ori_im, lang)->dict|None:
    # 解包
    paste_x, paste_y, xmin, ymin, xmax, ymax, _, _ = useful_list
    # 早期过滤
    if len(box_ocr_res) == 2:
        coords, (text, score) = box_ocr_res
        if score < OcrConfidence.min_confidence:
            return None
    else:
        coords = box_ocr_res
        text, score = "", 1

    p1, p2, p3, p4 = coords[0], coords[1], coords[2], coords[3]
    if (p3[0] - p1[0]) < OcrConfidence.min_width:
        return None

    # 角度校正
    poly = [p1, p2, p3, p4]
    if calculate_is_angle(poly):
        # 重新计算 p1-p4 坐标
        x_center = sum(pt[0] for pt in poly)/4
        y_center = sum(pt[1] for pt in poly)/4
        new_h = ((p4[1] - p1[1]) + (p3[1] - p2[1])) / 2
        new_w = p3[0] - p1[0]
        p1 = [x_center - new_w/2, y_center - new_h/2]
        p2 = [x_center + new_w/2, y_center - new_h/2]
        p3 = [x_center + new_w/2, y_center + new_h/2]
        p4 = [x_center - new_w/2, y_center + new_h/2]

    # 转换回原图坐标
    def adjust(pt):
        return [pt[0] - paste_x + xmin, pt[1] - paste_y + ymin]
    p1, p2, p3, p4 = adjust(p1), adjust(p2), adjust(p3), adjust(p4)

    result = {
        'category_id': 15,
        'poly': p1 + p2 + p3 + p4,
        'score': float(round(score, 2)),
        'text': text,
        'lang': lang
    }

    if ocr_enable and len(box_ocr_res) != 2:
        tmp_pt = copy.deepcopy(np.array([coords[0], coords[1], coords[2], coords[3]]).astype('float32'))
        img_crop = get_rotate_crop_image(ori_im, tmp_pt)
        result['np_img'] = img_crop

    return result