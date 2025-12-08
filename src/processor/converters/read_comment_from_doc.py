from docx import Document
from docx.oxml.ns import qn

def extract_comment_context(doc:Document, comment_id, context_chars=30):
    """
    提取被注释位置的上下文文本。
    :param filepath: Word 文件路径
    :param comment_id: 目标注释的整数 ID
    :param context_chars: 上下文中每侧提取字符数
    """
    comment = doc.comments.get(comment_id)
    if not comment:
        print(f"No comment found with ID {comment_id}")
        return

    print(f"Found comment: ID={comment.comment_id}, Author={comment.author}, Text={comment.text if comment.text else '[no content]'}\n")

    def get_neighbor_run(paragraph, idx):
        # 向左找
        left = ''
        for j in range(idx - 1, -1, -1):
            t = paragraph.runs[j]
            if t:
                left = t
                break
        return left

    for pi, para in enumerate(doc.paragraphs):
        for ri, run in enumerate(para.runs):
            elems = run._element.xpath('.//w:commentReference')
            if not elems:
                continue
            for ref in elems:
                rid = int(ref.get(qn('w:id')))
                if rid != comment.comment_id:
                    continue
                else:
                    run = get_neighbor_run(para, ri)
                    left = get_neighbor_run(para, ri).text
                    left_snip = left[-context_chars:] if left else "[No left context]"
                    print(f"commented content: '{left_snip}'")
                    print(f"comment content: '{comment.text}'")
