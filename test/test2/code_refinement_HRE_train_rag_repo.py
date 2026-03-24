# Qwen3-8B_RQ2-HRE-API.py
# -*- coding: utf-8 -*-
import json
import os
import re
import sys
import time
from typing import List, Dict, Any, Tuple

import numpy as np
import pandas as pd
from openai import OpenAI
from tqdm import tqdm

import torch
from transformers import AutoTokenizer, AutoModel

from eval_code_sim import calculate_exact_match, calculate_exact_match2, calculate_bleu_score, calculate_codebleu_score, \
    calculate_rouge_l_score, calculate_edit_progress

MODEL_DIR = "/Users/jiajunyu/llm_models/Qwen3-Embedding-0.6B"
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
BATCH_SIZE = 8
MAX_LENGTH = 4096



# =========================
# RHE
# =========================
def load_embedding_model(model_dir: str):
    tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)
    model = AutoModel.from_pretrained(
        model_dir,
        trust_remote_code=True,
        torch_dtype=torch.float32,
    )
    model = model.to(DEVICE)
    model.eval()
    return tokenizer, model


def mean_pooling(model_output, attention_mask):
    token_embeddings = model_output.last_hidden_state
    mask = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    emb = (token_embeddings * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
    return emb


def embed_texts(texts: List[str], tokenizer, model) -> List[np.ndarray]:
    start_time = time.time()
    all_embeddings = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        print(f"[embed] batch {i} - {min(i + BATCH_SIZE, len(texts))}/{len(texts)}", flush=True)

        encoded = tokenizer(
            batch,
            padding=True,
            truncation=True,
            return_tensors="pt",
            max_length=MAX_LENGTH,
        )
        encoded = {k: v.to(DEVICE) for k, v in encoded.items()}

        with torch.no_grad():
            out = model(**encoded)
            emb = mean_pooling(out, encoded["attention_mask"])
            emb = torch.nn.functional.normalize(emb, p=2, dim=1)
            emb = emb.detach().float().cpu().numpy()
            all_embeddings.append(emb)

        if DEVICE == "mps":
            torch.mps.empty_cache()
    elapsed_time = time.time() - start_time
    print(f"  [embed_texts] 嵌入 {len(texts)} 条文本，用时: {elapsed_time:.4f}s", file=sys.stderr)
    if all_embeddings:
        return np.vstack(all_embeddings).astype(np.float32)

    return np.zeros((0, model.config.hidden_size), dtype=np.float32)


def load_index_and_meta(index_path: str, meta_path: str, vec_path: str, RQ: str):
    start_time = time.time()
    import faiss
    idx = faiss.read_index(index_path)
    meta_list = []
    with open(meta_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                meta_list.append(json.loads(line.strip()))
            except Exception:
                meta_list.append({})
    vecs = np.load(vec_path)
    if len(meta_list) != vecs.shape[0]:
        raise ValueError(
            f"meta 数量 {len(meta_list)} 与 vec 数量{vecs.shape[0]}不一致"
        )
    if idx.ntotal != len(meta_list):
        raise ValueError(
            f"faiss index 数量 {idx.ntotal} 与 meta 数量 {len(meta_list)} 不一致"
        )
    text_to_vecs = {}
    for meta, vec in zip(meta_list, vecs):
        original_item = meta.get("original_item", {})
        if RQ == "RQ1":
            patch_text = original_item.get("patch")
        else:
            patch_text = original_item.get("old")
        if patch_text:
            text_to_vecs[patch_text] = vec.astype(np.float32)
    elapsed_time = time.time() - start_time
    print(f"  [load_index_and_meta] 加载索引和元数据，共 {len(meta_list)} 条，用时: {elapsed_time:.4f}s", file=sys.stderr)
    return idx, meta_list, text_to_vecs


def process_diff_code(diff_code: str) -> str:
    """
    处理包含'+'和'-'符号的diff格式代码
    
    Args:
        diff_code: 包含diff标记的代码字符串
    
    Returns:
        str: 修复后代码
            - 修复后代码: 包含'+'开头的行，不包含'-'开头的行
    """
    if not diff_code:
        return ""

    fixed_lines = []

    # 按行分割代码
    lines = diff_code.split('\n')

    for line in lines:
        # 移除行首的空白字符以便检查标记
        stripped_line = line.lstrip()

        if stripped_line.startswith('-'):
            # 修复后代码不包含这一行（全部去除）
            continue
        elif stripped_line.startswith('+'):
            # 修复后代码包含这一行（去掉'+'标记和可能的空白）
            fixed_content = line.replace('+', '', 1).lstrip()
            fixed_lines.append(fixed_content)
        else:
            # 两行都包含这一行（保持不变）
            fixed_lines.append(line)

    # 重新组合成字符串
    fixed_code = '\n'.join(fixed_lines)

    return fixed_code


### MODIFIED ###
def retrieve_and_rerank_experiences(
        index_path: str,
        meta_path: str,
        vec_path: str,
        query: str,
        RQ: str,
        tokenizer,
        model,
        top_k_anchors: int = 5,
):
    """
    模拟完整推理流程：
    1. 检索 top-K 锚点
    2. 收集所有经验（每个锚点可能有多个）
    3. 对每条经验，计算 sim(query, trigger_snippet) —— 若 trigger_snippet 为空，则用 anchor_diff
    4. 按该相似度重排序，返回 top-N 经验
    """
    total_start_time = time.time()
    idx, metas, text_to_vecs = load_index_and_meta(index_path, meta_path, vec_path, RQ)
    embed_start_time = time.time()
    q_vec = embed_texts([query], tokenizer, model).astype('float32')
    print(f"  [retrieve_and_rerank] 查询嵌入用时: {time.time() - embed_start_time:.4f}s", file=sys.stderr)
    D, I = idx.search(q_vec, top_k_anchors + 20)

    all_candidate_experiences = []
    had_code = set()

    if RQ == "RQ2":
        for score, pos in zip(D[0], I[0]):
            if pos < 0 or pos >= len(metas) or metas[pos]["original_item"]["old"] == query or \
                    metas[pos]["original_item"][
                        "old"] in had_code:
                continue
            patch_meta = metas[pos]["original_item"]
            old = patch_meta["old"]
            # old = process_diff_code(old)
            new = patch_meta["new"]
            new = process_diff_code(new)
            hunk = patch_meta["hunk"]
            comment = patch_meta["comment"]
            experiences = patch_meta.get("experiences", [])
            if not experiences or len(experiences) == 0:
                # 冷启动：用 anchor 自身作为唯一经验（无 trigger_by）
                all_candidate_experiences.append({
                    "comment": comment,
                    "diff_snippet": hunk,
                    "score": float(score),
                    "old": old,
                    "new": new,
                    "meta": patch_meta
                })
            elif len(experiences) == 1:
                all_candidate_experiences.append({
                    "experience": experiences[0]["experience"],
                    "comment": comment,
                    "diff_snippet": hunk,
                    "score": float(score),
                    "old": old,
                    "new": new,
                    "trigger_snippet": experiences[0]["trigger_snippet"],
                    "meta": patch_meta
                })
            else:
                # 找到具有最高score的经验
                best_exp = None
                best_score = -float('inf')
                best_trigger_diff = None
                for exp in experiences:
                    # ### KEY: 决定 ref_diff 用于重排序 ### 是谁触发了该经验的更新
                    trigger_diff = exp.get("trigger_snippet")
                    trigger_snippets = trigger_diff if isinstance(trigger_diff, list) else [trigger_diff]
                    valid_snippets = [s for s in trigger_snippets if s and s != query]
                    if not valid_snippets:
                        final_score = float(score)
                    else:
                        sim_scores = []
                        used_snippets = []
                    for snippet in valid_snippets:
                        # 这里不再在线embed
                        # 而是直接从text_to_vecs里取trigger 对应的向量
                        ref_vec = text_to_vecs.get(snippet)
                        if ref_vec is None:
                            continue
                        sim = float(np.dot(q_vec[0], ref_vec))
                        sim_scores.append(sim)
                        used_snippets.append(snippet)
                    if not sim_scores:
                        final_score = float(score)
                    elif len(sim_scores) == 1:
                        final_score = sim_scores[0]
                    else:  # 最后一个trigger 权重 0.5,其余 trigger 的均值权重 0.5
                        final_score = float(0.5 * sim_scores[-1] + 0.5 * np.mean(sim_scores[:-1]))
                    if final_score > best_score:
                        best_score = final_score
                        best_exp = exp
                        best_trigger_diff = valid_snippets

                # 只添加得分最高的经验
                if best_exp is not None:
                    all_candidate_experiences.append({
                        "experience": best_exp["experience"],
                        "comment": comment,
                        "diff_snippet": hunk,
                        "score": best_score,
                        "old": old,
                        "new": new,
                        "trigger_snippet": best_trigger_diff,
                        "meta": patch_meta
                    })
            had_code.add(old)

    # 过滤掉不包含"experience"字段的条目
    filtered_experiences = [exp for exp in all_candidate_experiences if "experience" in exp]

    # 按 score 降序排序
    filtered_experiences.sort(key=lambda x: x.get("score", 0), reverse=True)

    # 更新原列表
    all_candidate_experiences = filtered_experiences

    total_elapsed_time = time.time() - total_start_time
    print(
        f"  [retrieve_and_rerank] 总检索用时: {total_elapsed_time:.4f}s, 返回 {len(all_candidate_experiences[:top_k_anchors])} 条经验",
        file=sys.stderr)
    # 返回 top-N
    return all_candidate_experiences[:top_k_anchors]


def update_hre_experience(index_path, meta_path, experiences_str, RQ):
    start_time = time.time()
    experiences = json.loads(experiences_str)
    # 读取现有的元数据
    meta_list = []
    with open(meta_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                meta_list.append(json.loads(line.strip()))
            except Exception:
                meta_list.append({})

    # 将experiences转换为便于查找的字典
    exp_dict = {}
    if RQ == "RQ2":
        for exp in experiences:
            key = (exp.get("before_code"))
            exp_dict[key] = exp

    # 更新匹配的元数据条目
    updated_count = 0
    for meta_org in meta_list:
        meta_data_org = meta_org.get("original_item")
        key = ""
        if RQ == "RQ2":
            key = (meta_data_org.get("old"))
            # key = process_diff_code(key)
        if key in exp_dict and exp_dict[key]:
            if "experiences" not in meta_data_org:
                meta_data_org["experiences"] = []

            new_trigger = exp_dict[key]['trigger_snippet']
            old_trigger_snippets = exp_dict[key].get("old_trigger_snippets", [])
            trigger_snippets = old_trigger_snippets if isinstance(old_trigger_snippets, list) else [
                old_trigger_snippets]
            trigger_snippets.append(new_trigger)
            meta_data_org["experiences"].append({
                "experience": exp_dict[key]['experience'],
                "trigger_snippet": trigger_snippets
            })
            updated_count += 1

    # 写回更新后的元数据，不会新增数据，只会更新已有的meta条目
    with open(meta_path, 'w', encoding='utf-8') as f:
        for meta in meta_list:
            f.write(json.dumps(meta, ensure_ascii=False) + '\n')

    # 注意：这不会影响index_path，因为索引是基于代码片段的向量表示，
    # 而我们只更新了元数据中的经验信息，没有更改任何与索引相关的数据。
    elapsed_time = time.time() - start_time
    print(f"  [update_hre_experience] 更新 {updated_count} 条经验，用时: {elapsed_time:.4f}s", file=sys.stderr)
    return str({"updated_count": updated_count, "message": f"成功更新了{updated_count}条经验数据"})


def RHE_search_subprocess(RHE_index_path, RHE_meta_path, RHE_vec_path, tok, mod, query, top_k, operation, experiences,
                          RQ):
    start_time = time.time()
    if operation == "search":
        try:
            time0 = time.time()
            print(f"  [search] 开始执行")
            res = retrieve_and_rerank_experiences(RHE_index_path, RHE_meta_path, RHE_vec_path, query, RQ, tok, mod,
                                                  top_k_anchors=top_k)
            time1 = time.time() - time0
            print(f"  [search] 检索用时: {time1:.4f}s")
            # print(json.dumps(res, ensure_ascii=False))
        except Exception as e:
            print(json.dumps({"error": str(e)}), file=sys.stderr)
            sys.exit(1)
    elif operation == "update":
        try:
            time0 = time.time()
            print(f"  [update] 开始执行")
            res = update_hre_experience(RHE_index_path, RHE_meta_path, experiences, RQ)
            time1 = time.time() - time0
            print(f"  [update] 更新用时: {time1:.4f}s")
        except Exception as e:
            print(json.dumps({"error": str(e)}), file=sys.stderr)
            sys.exit(1)

    elapsed_time = time.time() - start_time
    return res, elapsed_time


# =========================
# Utils
# =========================
def ensure_dir(p: str):
    d = os.path.dirname(p) if os.path.splitext(p)[1] else p
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def save_xlsx_append(path: str, df_row: Dict[str, Any]):
    ensure_dir(path)
    if os.path.exists(path):
        df = pd.read_excel(path)
        df = pd.concat([df, pd.DataFrame([df_row])], ignore_index=True)
    else:
        df = pd.DataFrame([df_row])
    df.to_excel(path, index=False, engine="openpyxl")


def read_jsonl(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


# =========================
# LLM I/O
# =========================
def load_model():
    print("    初始化API客户端 ...")
    client = OpenAI(
        api_key="sk-9d0d07529d60432eaf9870cd62652c7f",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    print("    API客户端就绪")
    return client


def gen_with_messages(messages, client) -> Tuple[str, str, float, int, int, list, str]:
    start_time = time.time()
    completion = client.chat.completions.create(
        model="qwen3.5-plus",
        messages=messages,
        extra_body={"enable_thinking": False},
        stream=False
    )

    elapsed_time = time.time() - start_time
    text = completion.choices[0].message.content

    input_tokens = completion.usage.prompt_tokens if hasattr(completion, 'usage') and completion.usage else 0
    output_tokens = completion.usage.completion_tokens if hasattr(completion, 'usage') and completion.usage else 0

    think_pattern = r"</think>(.*?)</think>"
    think_match = re.search(think_pattern, text, re.DOTALL)
    think_content = think_match.group(1).strip() if think_match else ""

    output_pattern = r"</think>(.*?)<\|im_end\|>"
    output_match = re.search(output_pattern, text, re.DOTALL)
    output_content = output_match.group(1).strip() if output_match else text.strip()

    lines = output_content.splitlines()
    if len(lines) >= 2 and lines[0].strip().lower() == "```json" and lines[-1].strip() == "```":
        output_content = "\n".join(lines[1:-1])

    return think_content, output_content, elapsed_time, input_tokens, output_tokens, messages, text


def trim_text_to_tokens_use_before_code(text: str, before_code: str) -> str:
    if not text:
        return text, None
    if len(text) > 409600:
        print(f"     原始长度 {len(text)} -> 过长删除后的长度 409600")
        return None, None
    return text, None


def generate_refinement_code(before_code, review_comment, repo, client):
    history_repair_experiences, search_time = RHE_search_subprocess(RHE_index_path, RHE_meta_path, RHE_vec_path, tok,
                                                                    mod,
                                                                    before_code, TOPK_HRE, "search", "", "RQ2")
    hre_block = ""
    experiences = []
    if history_repair_experiences:
        for i, meta_data in enumerate(history_repair_experiences, 1):
            candidate_snippet = (meta_data.get("old") or "")
            historical_comment = (meta_data.get("comment") or "")
            diff_snippet = meta_data.get("diff_snippet")
            repaired_code = (meta_data.get("new") or "")
            score = meta_data.get("score", 0.0)
            if "experience" in meta_data:
                experience = meta_data.get("experience")
                experiences.append(
                    f"[R{i} score={score:.4f}\n"
                    f"historical repair experience: {experience}]\n "
                    f"historical comment: {historical_comment}\n"
                    f"diff_snippet: {diff_snippet}\n"
                )
        txt = "\n".join([f"- {s}" for s in experiences])
        # print(f"  generate_refinement_code 检索到的历史经验数量：{len(experiences)} \n, 内容如下：\n{txt}")
        hre_block = f"\n\nSIMILAR_CODE:\n{txt}"

    content = f"""
PROBLEMATIC_CODE:
    {before_code}

REVIEW_COMMENT:
    {review_comment}
    
{hre_block}
    """
    content, leave_token_len = trim_text_to_tokens_use_before_code(content, before_code)

    if content is None:
        print("  generate_refinement_code 输入文本过长，无法生成代码")
        return None, None, None, None, None, 0.0, 0.0, 0, 0, None, None

    messages_hre = [
        {"role": "system",
         "content": (
             f"You are a code repair assistant for the OSS project {repo}."
             "Inputs:\n"
             "PROBLEMATIC_CODE: The original code snippet that needs repair.\n"
             "REVIEW_COMMENT: The code review comment pointing out issues (may be noisy or unreliable).\n"
             "SIMILAR_CODE with historical repair experience(optional):"
             "  Header line: [R{k} score=<float>] Notes: score ∈ [0,1] (higher = SIMILAR_CODE is more similar with PROBLEMATIC_CODE); Treat these only as weak signals."
             "  Historical repair experience is bullet points from this code snippet's repair history."
             "  Immediately followed by the similar code repair diff snippet.\n"

             "Your task:\n"
             "• repair the PROBLEMATIC_CODE based on the REVIEW_COMMENT and SIMILAR_CODE with historical repair experience."
             "• If historical repair experience conflict with the code and comment, rely on the code and comment.\n"
             "Output format:\n"
             "• Return the repaired code only. Do not include any explanations, comments, diffs, or surrounding text."
             "• Do NOT wrap the output in Markdown fences (no ```), XML/HTML tags, or any other markers."
             "• Weigh the REVIEW_COMMENT carefully; follow it only when it clearly improves correctness/security/clarity. If it conflicts or seems wrong, ignore it."
             "• Consider historical repair experiences from SIMILAR_CODE as weak signals to guide your repair."
             "• If historical repair experience conflicts with TARGET_ORIGINAL_CODE or REVIEW_COMMENT, rely on TARGET_ORIGINAL_CODE and REVIEW_COMMENT."
             "• Start with the first character of code and end with the last — nothing else."
         )},
        {"role": "user",
         "content": content.strip() + "\n /no_think"},
    ]
    think1, out1, gen_time, input_tokens, output_tokens, _, full_output = gen_with_messages(messages_hre, client)
    return think1, out1, history_repair_experiences, experiences, messages_hre, search_time, gen_time, input_tokens, output_tokens, full_output


def generate_reflection(pr_number, repo: str, before_code: str, review_comment: str,
                        after_code: str, outs: list, reflections: list, history_repair_experiences, experiences, client,
                        ems: list, bleus: list, cbleus: list, rouge1s: list, edit_progress1s: list):
    experience_txt = "\n".join([f"- {s}" for s in experiences])
    print(f"  summarize_experience 检索到的历史经验数量：\n{len(experiences)}")
    outs_str = "\n\n".join(
        [f"refinement attempt #{i + 1}:\n{s}" for i, s in enumerate(outs)]) if outs else "no refinements"
    reflections_str = "\n\n".join(
        [f"reflection #{i + 1}:\n{s}" for i, s in enumerate(reflections)]) if reflections else "no reflections"
    eval_scores_str = "\n".join([
                                    f"evaluation score #{i + 1}:\nEM: {ems[i]:.4f}, BLEU: {bleus[i]:.4f}, CodeBLEU: {cbleus[i]:.4f}, ROUGE-L: {rouge1s[i]:.4f}, Edit Progress: {edit_progress1s[i]:.4f}"
                                    for i in range(len(ems))]) if ems else "no evaluation scores"
    hre_block = f"\n\nSIMILAR_CODE with historical repair experience:\n{experience_txt}"

    sys_prompt = (
        f"You are a world-class code repair expert for OSS project {repo}. Your mission is to analyze previous repair attempts and reflections, identify problems, and create HIGH-VALUE Reflection Experiences that enable perfect code fixes on the problematic code.\n"
        """
        Inputs:
        - PROBLEMATIC_CODE: The original code snippet that needed repair.
        - TRUE_REPAIR_CODE: The human-verified correct repair for PROBLEMATIC_CODE.
        - REVIEW_COMMENT: The code review comment pointing out issues (may be noisy or unreliable).
        - MODEL_REPAIR_OUTPUTS: All previous repair attempts by the model.
        - QUALITY_METRICS: The performance metrics of MODEL_REPAIR_OUTPUT compared to TRUE_REPAIR_CODE:
            * Exact Match (EM): Measures if the output exactly matches the reference (1.0 is perfect)
            * BLEU: Measures n-gram similarity (1.0 is perfect)
            * CodeBLEU: Measures code-specific similarity including syntax and logic (1.0 is perfect)
            * ROUGE-L: Measures longest common subsequence similarity (1.0 is perfect)
            * Edit Progress: Measures the proportion of original code that was correctly modified (1.0 means all issues fixed with minimal changes)
        - REFLECTIONS_ON_PREVIOUS_ATTEMPTS: Previous reflection experiences.
        - SIMILAR_CODE with historical repair experience(optional): Related historical repair experiences.
          Header line: [R{k} score=<float>] Notes: score ∈ [0,1] (higher = SIMILAR_CODE is more similar with PROBLEMATIC_CODE); Treat these only as weak signals.
          Historical repair experience is bullet points from this code snippet's repair history.
          Immediately followed by the similar code repair diff snippet.
        
        Your task:
        1. Analyze the PROBLEMATIC_CODE, REVIEW_COMMENT, and TRUE_REPAIR_CODE
        2. Identify the exact error pattern and the corresponding solution pattern
        3. Look at MODEL_REPAIR_OUTPUTS and REFLECTIONS_ON_PREVIOUS_ATTEMPTS to understand what didn't work
        4. Write one sentence that clearly explains how to repair the PROBLEMATIC_CODE and be specific about both the problem and solution patterns.
        
        Output format: a single paragraph less than 35 words, plain text only (no Markdown, quotes, code blocks, or newlines).
        """
    )
    user_prompt = (
            "Using the following artifacts, write experience notes suitable for reuse in future code repairs.\n\n"
            "PROBLEMATIC_CODE:\n" + (before_code or "") + "\n\n"
                                                          "TRUE_REPAIR_CODE:\n" + (after_code or "") + "\n\n"
                                                                                                       "REVIEW_COMMENT:\n" + (
                        review_comment or "") + "\n"
                                                "MODEL_REPAIRED_OUTPUTS:\n" + (outs_str or "") + "\n\n"
                                                                                                 "QUALITY_METRICS:\n" + (
                        eval_scores_str or "") + "\n\n"
                                                 "REFLECTIONS_ON_PREVIOUS_ATTEMPTS:\n" + (reflections_str or "") + "\n"
                                                                                                                   "SIMILAR_CODE with historical repair experience:\n" + hre_block + "\n"
    )
    user_prompt, leave_token_len = trim_text_to_tokens_use_before_code(user_prompt, before_code)
    if user_prompt is None:
        print("  summarize_experience 输入文本过长，无法生成经验")
        return "", 0.0, 0, 0, None, None

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt + "\n /no_think"}
    ]
    _, summary_experiences, gen_time, input_tokens, output_tokens, _, full_output = gen_with_messages(messages, client)

    return summary_experiences, gen_time, input_tokens, output_tokens, messages, full_output


def generate_fix_with_reflection(pr_number, repo: str, before_code: str, review_comment: str,
                                 after_code: str, outs: list, reflections: list, history_repair_experiences,
                                 experiences, client, ems: list, bleus: list, cbleus: list, rouge1s: list,
                                 edit_progress1s: list):
    txt = "\n".join([f"- {s}" for s in experiences])
    # print(f"  generate_refinement_code 检索到的历史经验数量：{len(experiences)} \n, 内容如下：\n{txt}")
    outs_str = "\n\n".join(
        [f"refinement attempt #{i + 1}:\n{s}" for i, s in enumerate(outs)]) if outs else "no refinements"
    reflections_str = "\n\n".join(
        [f"reflection #{i + 1}:\n{s}" for i, s in enumerate(reflections)]) if reflections else "no reflections"
    eval_scores_str = "\n".join([
                                    f"evaluation score #{i + 1}:\nEM: {ems[i]:.4f}, BLEU: {bleus[i]:.4f}, CodeBLEU: {cbleus[i]:.4f}, ROUGE-L: {rouge1s[i]:.4f}, Edit Progress: {edit_progress1s[i]:.4f}"
                                    for i in range(len(ems))]) if ems else "no evaluation scores"
    hre_block = f"\n\nSIMILAR_CODE with historical repair experience:\n{txt}"
    reflection_block = f"\n\nREFLECTION_ON_PREVIOUS_ATTEMPTS:\n{reflections_str}"
    previous_output_block = f"\n\nPREVIOUS_REPAIR_ATTEMPTS:\n{outs_str}"
    eval_scores_block = f"\n\nQUALITY METRICS:\n{eval_scores_str}"

    content = f"""
PROBLEMATIC_CODE:
```
{before_code}
```
REVIEW_COMMENT:
```
{review_comment}
```
{previous_output_block}
{eval_scores_block}
{reflection_block}    
{hre_block}
    """
    content, leave_token_len = trim_text_to_tokens_use_before_code(content, before_code)

    if content is None:
        print("  输入文本过长，无法生成代码")
        return None, None, None, 0.0, 0, 0

    messages = [
        {"role": "system",
         "content": (
             f"You are a code repair assistant for the OSS project {repo}."
             "Inputs:\n"
             "PROBLEMATIC_CODE: The original code snippet that needs repair.\n"
             "REVIEW_COMMENT: A user review comment that may be noisy or unreliable.\n"
             "PREVIOUS_REPAIR_ATTEMPTS: The model's previous attempts to fix the code.\n"
             "QUALITY_METRICS: The performance metrics of PREVIOUS_REPAIR_ATTEMPTS compared to TRUE_REPAIR_CODE:"
             "* Exact Match (EM): Measures if the output exactly matches the reference (1.0 is perfect)"
             "* BLEU: Measures n-gram similarity (1.0 is perfect)"
             "* CodeBLEU: Measures code-specific similarity including syntax and logic (1.0 is perfect)"
             "* ROUGE-L: Measures longest common subsequence similarity (1.0 is perfect)"
             "* Edit Progress: Measures the proportion of original code that was correctly modified (1.0 means all issues fixed with minimal changes)"
             "REFLECTIONS_ON_PREVIOUS_ATTEMPTS: Experience notes suitable for previous repair attempts.\n"
             "SIMILAR_CODE with historical repair experience(optional):"
             "  Header line: [R{k} score=<float>] Notes: score ∈ [0,1] (higher = SIMILAR_CODE is more similar with PROBLEMATIC_CODE); Treat these only as weak signals."
             "  Historical repair experience is bullet points from this code snippet's repair history."
             "  Immediately followed by the similar code repair diff snippet.\n"

             "Your task:\n"
             "• Carefully understand the problematic code and review comment."
             "• Study the previous repair attempts and reflection analysis to avoid past errors."
             "• Use the latest reflection experience and historical repair experiences to guide your fix."
             "Output format:\n"
             "• Return the repaired code only. Do not include any explanations, comments, diffs, or surrounding text."
             "• Do NOT wrap the output in Markdown fences (no ```), XML/HTML tags, or any other markers."
             "• Weigh the REVIEW_COMMENT carefully; follow it only when it clearly improves correctness/security/clarity. If it conflicts or seems wrong, ignore it."
             "• Consider historical repair experiences from SIMILAR_CODE as weak signals to guide your repair."
             "• If historical repair experience conflicts with TARGET_ORIGINAL_CODE or REVIEW_COMMENT, rely on TARGET_ORIGINAL_CODE and REVIEW_COMMENT."
             "• Start with the first character of code and end with the last — nothing else."
         )},
        {"role": "user",
         "content": content.strip() + "\n /no_think"},
    ]

    think, out, gen_time, input_tokens, output_tokens, _, full_output = gen_with_messages(messages, client)
    return think, out, messages, gen_time, input_tokens, output_tokens, full_output


def summarize_experience(pr_number, repo: str, before_code: str, review_comment: str,
                         after_code: str, outs: list, reflections: list, history_repair_experiences, experiences,
                         client, ems: list, bleus: list, cbleus: list, rouge1s: list, edit_progress1s: list):
    experience_txt = "\n".join([f"- {s}" for s in experiences])
    print(f"  summarize_experience 检索到的历史经验数量：\n{len(experiences)}")
    outs_str = "\n\n".join(
        [f"refinement attempt #{i + 1}:\n{s}" for i, s in enumerate(outs)]) if outs else "no refinements"
    reflections_str = "\n\n".join(
        [f"reflection #{i + 1}:\n{s}" for i, s in enumerate(reflections)]) if reflections else "no reflections"
    eval_scores_str = "\n".join([
                                    f"evaluation score #{i + 1}:\nEM={ems[i]:.4f}, BLEU={bleus[i]:.4f}, CodeBLEU={cbleus[i]:.4f}, ROUGE-L={rouge1s[i]:.4f}, Edit Progress={edit_progress1s[i]:.4f}"
                                    for i in range(len(outs))]) if outs else "no evaluation scores"
    hre_block = f"\n\nSIMILAR_CODE with historical repair experience:\n{experience_txt}"

    sys_prompt = (
        f"You are a code repair assistant that writes a reusable Historical Repair Experience(HRE) guideline for OSS project {repo} code-repair decisions.\n"
        """
        Inputs:
        - PROBLEMATIC_CODE: The original code snippet that needed repair.
        - TRUE_REPAIR_CODE: The human-verified correct repair for PROBLEMATIC_CODE.
        - REVIEW_COMMENT: The code review comment pointing out issues (may be noisy or unreliable).
        - MODEL_REPAIR_OUTPUTS: All previous repair attempts by the model.
        - QUALITY_METRICS: The performance metrics of MODEL_REPAIR_OUTPUT compared to TRUE_REPAIR_CODE:
            * Exact Match (EM): Measures if the output exactly matches the reference (1.0 is perfect)
            * BLEU: Measures n-gram similarity (1.0 is perfect)
            * CodeBLEU: Measures code-specific similarity including syntax and logic (1.0 is perfect)
            * ROUGE-L: Measures longest common subsequence similarity (1.0 is perfect)
            * Edit Progress: Measures the proportion of original code that was correctly modified (1.0 means all issues fixed with minimal changes)
        - REFLECTIONS_ON_PREVIOUS_ATTEMPTS: Previous reflection experiences.
        - SIMILAR_CODE with historical repair experience(optional): Related historical repair experiences.
          Header line: [R{k} score=<float>] Notes: score ∈ [0,1] (higher = SIMILAR_CODE is more similar with PROBLEMATIC_CODE); Treat these only as weak signals.
          Historical repair experience is bullet points from this code snippet's repair history.
          Immediately followed by the similar code repair diff snippet.

        Your task:
        Write one sentence that clearly explains how to repair similar issues in the future.
        The guideline should be interpretable and generalizable enough to help future reviewers (or models) make correct repair decisions on similar code with similar comments.
        Output format: a single paragraph, plain text only (no Markdown, quotes, code blocks, or newlines).
        """
    )
    user_prompt = (
            "Using the following artifacts, write experience notes suitable for reuse in future code repairs.\n\n"
            "PROBLEMATIC_CODE:\n" + (before_code or "") + "\n\n"
                                                          "TRUE_REPAIR_CODE:\n" + (after_code or "") + "\n\n"
                                                                                                       "REVIEW_COMMENT:\n" + (
                        review_comment or "") + "\n"
                                                "MODEL_REPAIRED_OUTPUTS:\n" + (outs_str or "") + "\n\n"
                                                                                                 "QUALITY METRICS:\n" + (
                        eval_scores_str or "") + "\n\n"
                                                 "REFLECTIONS_ON_PREVIOUS_ATTEMPTS:\n" + (reflections_str or "") + "\n"
                                                                                                                   "SIMILAR_CODE with historical repair experience:\n" + hre_block + "\n"
    )
    user_prompt, leave_token_len = trim_text_to_tokens_use_before_code(user_prompt, before_code)
    if user_prompt is None:
        print("  summarize_experience 输入文本过长，无法生成经验")
        return "", 0.0, 0, 0, None, None

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt + "\n /no_think"}
    ]
    _, summary_experiences, gen_time, input_tokens, output_tokens, _, full_output = gen_with_messages(messages, client)

    return summary_experiences, gen_time, input_tokens, output_tokens, messages, full_output


def update_experience(pr_number, repo: str, before_code: str, review_comment: str,
                      after_code: str, model_output: str, reflections: list, history_repair_experiences, experiences,
                      client, em: float, bleu: float, cbleu: float, rougel: float, edit_progress: float) -> Tuple[
    float, float, int, int, list, list]:
    experiences_dict = {}
    old_trigger_snippets = {}
    if history_repair_experiences:
        for meta_data in history_repair_experiences:
            if "experience" in meta_data and meta_data["experience"] is not None:
                before_code_temp = meta_data["old"]
                experience = meta_data["experience"]
                key = before_code_temp
                experiences_dict[key] = experience
                old_trigger_snippets[key] = meta_data.get("trigger_snippet", [])
    if experiences_dict.__len__() == 0:
        print(f"  仓库{repo},中{before_code}没有找到历史经验，跳过更新")
        return 0.0, 0.0, 0, 0, [], []
    print(f"  update_experience 检索到的历史经验数量：{len(experiences_dict)}")
    update_experiences_list = []

    total_gen_time = 0.0
    total_input_tokens = 0
    total_output_tokens = 0
    prompts = []
    outputs = []

    for key, candidate_experience in experiences_dict.items():
        print(f"     正在处理第{key[0]}的历史经验 更新")
        sys_prompt = (
            f"""
            You are a code repair assistant that refines an existing Historical Repair Experience (HRE) guideline for the open-source project {repo}.
            Inputs:
            - HISTORICAL_REPAIR_EXPERIENCE: The current guideline, derived from past repair decisions.
            - PROBLEMATIC_CODE: A new original code snippet that needs repair.
            - REVIEW_COMMENT: A comment from a code reviewer about PROBLEMATIC_CODE.
            - MODEL_REPAIR_OUTPUT: Model's repair output for PROBLEMATIC_CODE using the current guideline.
            - TRUE_REPAIR_CODE: The human-verified correct repair for PROBLEMATIC_CODE.
            - QUALITY_METRICS: The performance metrics of MODEL_REPAIR_OUTPUT compared to TRUE_REPAIR_CODE:
                * Exact Match (EM): Measures if the output exactly matches the reference (1.0 is perfect)
                * BLEU: Measures n-gram similarity (1.0 is perfect)
                * CodeBLEU: Measures code-specific similarity including syntax and logic (1.0 is perfect)
                * ROUGE-L: Measures longest common subsequence similarity (1.0 is perfect)
                * Edit Progress: Measures the proportion of original code that was correctly modified (1.0 means all issues fixed with minimal changes)
            
            Your task:
            Revise the HISTORICAL_REPAIR_EXPERIENCE *minimally* to incorporate insights from the new PROBLEMATIC_CODE and REVIEW_COMMENT.
            The revised rule should help future models correctly repair similar code snippets in {repo}.
            If the current model output has low quality metrics, identify what aspects of the repair were incorrect and adjust the guideline accordingly.
            Preserve the core insights from the original guideline while adapting it to the new context.
            Output format: a single paragraph, plain text only (no Markdown, quotes, code blocks, or newlines).
            """
        )
        user_prompt = (
                "HISTORICAL_REPAIR_EXPERIENCE:\n" + candidate_experience + "\n\n"
                                                                           "PROBLEMATIC_CODE:\n" + (
                            before_code or "") + "\n\n"
                                                 "REVIEW_COMMENT:\n" + (review_comment or "") + "\n\n"
                                                                                                "MODEL_REPAIR_OUTPUT:\n" + (
                            model_output or "") + "\n\n"
                                                  "TRUE_REPAIR_CODE:\n" + (after_code or "") + "\n\n"
                                                                                               "QUALITY_METRICS:\n" +
                f"EM: {em:.4f}\n" +
                f"BLEU: {bleu:.4f}\n" +
                f"CodeBLEU: {cbleu:.4f}\n" +
                f"ROUGE-L: {rougel:.4f}\n" +
                f"Edit Progress: {edit_progress:.4f}\n"
                "Decide and output the FINAL EXPERIENCE TEXT now."
        )
        user_prompt, leave_token_len = trim_text_to_tokens_use_before_code(user_prompt, before_code)

        if user_prompt is None:
            print("  update_experience 输入文本过长，无法生成经验")
            continue

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt + "\n /no_think"}
        ]

        _, update_experiences, update_time, update_input_tokens, update_output_tokens, _, full_output \
            = gen_with_messages(messages, client)
        total_gen_time += update_time
        total_input_tokens += update_input_tokens
        total_output_tokens += update_output_tokens
        prompts.append(messages)
        outputs.append(full_output)

        update_experiences_list.append({
            "before_code": key,
            "trigger_snippet": before_code,
            "old_trigger_snippets": old_trigger_snippets[key],
            "experience": update_experiences,
        })

    try:
        update_experience_str = json.dumps(update_experiences_list, ensure_ascii=False)
        json.loads(update_experience_str)
    except (TypeError, ValueError) as e:
        print(f"     update_experience无法被json化: {e}")
        update_experience_str = "[]"
    result, update_rhe_time = RHE_search_subprocess(RHE_index_path, RHE_meta_path, RHE_vec_path, tok, mod,
                                                    before_code, TOPK_HRE, "update", str(update_experience_str), "RQ2")
    print(f"  更新经验的结果：{result}")
    return total_gen_time, update_rhe_time, total_input_tokens, total_output_tokens, prompts, outputs


if __name__ == "__main__":
    REPO_List = [
        "space-wizards-space-station-14",
        # "Dolibarr-dolibarr",
        # "communication_netmanager_base",
        # "arkui_ace_engine",
        # "ability_ability_runtime",
        # "apache-beam",
        # "EOSIO-eos",
        # "home-assistant-core",
        # "mulesoft-mule",
        # "pachyderm-pachyderm",
        # "ray-project-ray",
        # "tikv-pd",
    ]

    tok, mod = load_embedding_model(MODEL_DIR)
    gen_client = load_model()

    TOPK_HRE = 5
    MAX_RETRIES = 3
    TARGET_THRESHOLD = 0.8

    for repo in REPO_List:
        DATA_PATH = f"./repo_data2/{repo}/{repo}_train.jsonl"

        RHE_index_path = f"./hre/{repo}/{repo}_code_refinement_hre_index_plus_0.faiss"
        RHE_meta_path = f"./hre/{repo}/{repo}_code_refinement_hre_meta_plus_0.jsonl"
        RHE_vec_path = f"./hre/{repo}/{repo}_code_refinement_hre_vec_plus_0.npy"

        RESULT_XLSX = f"./result/rq2/{repo}/{repo}_qwen3_8B_train_HRE_outputs_plus_0.xlsx"
        METRIC_FILE = f"./result/rq2/{repo}/{repo}_qwen3_8B_train_HRE_metrics_plus_0.txt"

        ensure_dir(RESULT_XLSX)
        data = read_jsonl(DATA_PATH)

        processed_repo_pr_code = set()
        if os.path.exists(RESULT_XLSX):
            existing_df = pd.read_excel(RESULT_XLSX)
            for _, row in existing_df.iterrows():
                repo_name = row['repo']
                before_code = row['before_code']
                processed_repo_pr_code.add((repo_name, before_code))

        results = []

        for item in tqdm(data, desc="RQ2-HRE processing", unit="item"):
            start_time = time.time()
            pr_number = item.get("ghid", item.get("id", "unknown_pr"))
            repo = item.get("proj")
            before_code = item.get("old") or ""
            input = process_diff_code(before_code)
            lang = item.get("lang", "unknown")

            check_done_key = (repo, before_code)
            if check_done_key in processed_repo_pr_code:
                print(f"      跳过已处理样本：仓库 {repo}，before code {before_code}。")
                continue

            after_code = item.get("new") or ""
            after_code = process_diff_code(after_code)
            print(f"      仓库 {repo}，before code {before_code}，after code {after_code}")
            review_comment = item.get("comment") or ""
            print(f"      仓库 {repo}，before code {before_code}，修复开始=======================")

            if not item.get("y", 1):
                print(f"      跳过不需要检查的样本：仓库 {repo}，PR号 {pr_number}。========================")
                continue

            think1, out1, history_repair_experiences, experiences, messages_hre, search_time, gen_time, \
                input_tokens, output_tokens, gen0_full_output = generate_refinement_code(before_code,
                                                                                         review_comment,
                                                                                         repo,
                                                                                         gen_client)
            if not think1 and not out1 and not history_repair_experiences and not messages_hre:
                print(f"      仓库 {repo}，PR号 {pr_number}，修复异常")
                continue
            print(f"      仓库 {repo}，PR号 {pr_number}，修复结果结束")
            outs = []
            new_out = out1
            reflections = []
            reflection = ""
            eval_scores = []
            outs.append(out1)
            ems = []
            em2s = []
            bleus = []
            cbleus = []
            rouges = []
            edit_progresses = []
            reflection_times = []
            reflection_input_tokens_list = []
            reflection_output_tokens_list = []
            gen_times = [gen_time]
            gen_input_tokens_list = [input_tokens]
            gen_output_tokens_list = [output_tokens]
            retry = 0
            # 存储所有模型prompts和outputs
            gen_prompts = [messages_hre]
            gen_outputs = [gen0_full_output]
            reflection_prompts = []
            reflection_outputs = []
            em = calculate_exact_match(out1, after_code)
            em2 = calculate_exact_match2(out1, after_code)
            bleu = calculate_bleu_score(out1, after_code)
            cbleu = calculate_codebleu_score(out1, after_code, lang, repo)
            rouge = calculate_rouge_l_score(out1, after_code)
            edit_progress = calculate_edit_progress(input, out1, after_code)
            ems.append(em)
            em2s.append(em2)
            bleus.append(bleu)
            cbleus.append(cbleu)
            rouges.append(rouge)
            edit_progresses.append(edit_progress)

            update_output = out1
            update_cbleu = cbleu
            update_em = em
            update_bleu = bleu
            update_rouge = rouge
            update_edit_progress = edit_progress

            for retry_count in range(MAX_RETRIES):
                if cbleu >= TARGET_THRESHOLD:
                    print(
                        f"      仓库 {repo}，PR号 {pr_number}，第{retry_count}次尝试达到目标阈值({cbleu:.4f} >= {TARGET_THRESHOLD:.4f})，修复成功")
                    break
                print(f"第{retry_count}次尝试未达到目标阈值({cbleu:.4f} < {TARGET_THRESHOLD:.4f})，开始反思重试...")
                retry += 1
                reflection, reflection_time, reflection_input_tokens, reflection_output_tokens, reflection_prompt, \
                    reflection_full_output = generate_reflection(pr_number, repo, before_code, review_comment,
                                                                 after_code, outs, reflections,
                                                                 history_repair_experiences, experiences,
                                                                 gen_client,
                                                                 ems, bleus, cbleus, rouges, edit_progresses)
                reflections.append(reflection)
                reflection_times.append(reflection_time)
                reflection_input_tokens_list.append(reflection_input_tokens)
                reflection_output_tokens_list.append(reflection_output_tokens)
                reflection_prompts.append(reflection_prompt)
                reflection_outputs.append(reflection_full_output)

                think, new_out, messages, gen_time, input_tokens, output_tokens, gen_full_output = \
                    generate_fix_with_reflection(pr_number, repo, before_code, review_comment, after_code, outs,
                                                 reflections,
                                                 history_repair_experiences, experiences,
                                                 gen_client,
                                                 ems, bleus, cbleus, rouges, edit_progresses)
                if not think and not new_out:
                    print(f"  第{retry}次反思修复生成失败，返回之前的结果")
                    continue

                gen_times.append(gen_time)
                gen_input_tokens_list.append(input_tokens)
                gen_output_tokens_list.append(output_tokens)
                gen_prompts.append(messages)
                gen_outputs.append(gen_full_output)
                outs.append(new_out)
                em = calculate_exact_match(new_out, after_code)
                em2 = calculate_exact_match2(new_out, after_code)
                bleu = calculate_bleu_score(new_out, after_code)
                cbleu = calculate_codebleu_score(new_out, after_code, lang, repo)
                rouge = calculate_rouge_l_score(new_out, after_code)
                edit_progress = calculate_edit_progress(input, new_out, after_code)

                ems.append(em)
                em2s.append(em2)
                bleus.append(bleu)
                cbleus.append(cbleu)
                rouges.append(rouge)
                edit_progresses.append(edit_progress)
                if cbleu > update_cbleu:
                    update_output = new_out
                    update_cbleu = cbleu
                    update_em = em
                    update_bleu = bleu
                    update_rouge = rouge
                    update_edit_progress = edit_progress
                if cbleu >= TARGET_THRESHOLD:
                    print(f"  达到目标阈值({cbleu:.4f} ≥ {TARGET_THRESHOLD:.4f})，修复完成")
                    break

            print(f"      仓库 {repo}，PR号 {pr_number}，第{retry}次尝试反思修复CodeBLEU得分：{cbleu:.4f}")
            print(f"      仓库 {repo}，PR号 {pr_number}，总结经验开始")
            summarized_experience, summarize_time, summarize_input_tokens, summarize_output_tokens, summarize_prompt, \
                summarize_full_output = summarize_experience(pr_number, repo, before_code, review_comment, after_code,
                                                             outs, reflections,
                                                             history_repair_experiences, experiences,
                                                             gen_client,
                                                             ems, bleus, cbleus, rouges, edit_progresses)
            update_experience_list = [{
                "before_code": before_code,
                "trigger_snippet": before_code,
                "experience": summarized_experience,
            }]

            try:
                update_experience_str = json.dumps(update_experience_list, ensure_ascii=False)
                json.loads(update_experience_str)
            except (TypeError, ValueError) as e:
                print(f"     update_experience无法被json化: {e}")
                update_experience_str = "[]"

            result, save_exp_time = RHE_search_subprocess(RHE_index_path, RHE_meta_path, RHE_vec_path, tok, mod,
                                                          before_code, TOPK_HRE, "update", update_experience_str, "RQ2")
            print(f"  保存经验的结果：{result}")

            print(f"      仓库 {repo}，PR号 {pr_number}，update_experience 开始")
            if update_cbleu >= 0.95:
                print("模型预测Codebleu>=0.95，无需更新经验，只追加")
            else:
                update_gen_time, update_rhe_time, update_exp_input_tokens, update_exp_output_tokens, update_prompts, update_outputs = \
                    update_experience(pr_number, repo, before_code, review_comment, after_code, update_output,
                                      reflections,
                                      history_repair_experiences, experiences,
                                      gen_client,
                                      update_em, update_bleu, update_cbleu, update_rouge, update_edit_progress)

            processing_time = time.time() - start_time
            print(f"      仓库 {repo}，PR号 {pr_number}，总处理时间：{processing_time:.4f} 秒")

            row = {
                "pr_number": pr_number,
                "repo": repo,
                "before_code": before_code,
                "review_comment": review_comment,
                "prompt_with_hre": messages_hre,
                "think_with_hre": think1,
                "output_with_hre": outs[0],
                "after_code": after_code,
                "EM_hre": ems[0],
                "EM2_hre": em2s[0],
                "BLEU_hre": bleus[0],
                "CodeBLEU_hre": cbleus[0],
                "ROUGE-L_hre": rouges[0],
                "Edit_Progress_hre": edit_progresses[0],
                "Processing_Time_Seconds": processing_time,
                "retry_count": retry,
                "search_time": search_time,
                "gen0_time": gen_times[0] if len(gen_times) > 0 else 0.0,
                "gen0_input_tokens": gen_input_tokens_list[0] if len(gen_input_tokens_list) > 0 else 0,
                "gen0_output_tokens": gen_output_tokens_list[0] if len(gen_output_tokens_list) > 0 else 0,
                "gen0_prompt": gen_prompts[0] if len(gen_prompts) > 0 else None,
                "gen0_full_output": gen_outputs[0] if len(gen_outputs) > 0 else None,
                "reflection1_time": reflection_times[0] if len(reflection_times) > 0 else 0.0,
                "reflection1_input_tokens": reflection_input_tokens_list[0] if len(
                    reflection_input_tokens_list) > 0 else 0,
                "reflection1_output_tokens": reflection_output_tokens_list[0] if len(
                    reflection_output_tokens_list) > 0 else 0,
                "reflection1_prompt": reflection_prompts[0] if len(reflection_prompts) > 0 else None,
                "reflection1_full_output": reflection_outputs[0] if len(reflection_outputs) > 0 else None,

                # 第一次反思后的指标（对应gen1的输出）
                "gen1_time": gen_times[1] if len(gen_times) > 1 else 0.0,
                "gen1_input_tokens": gen_input_tokens_list[1] if len(gen_input_tokens_list) > 1 else 0,
                "gen1_output_tokens": gen_output_tokens_list[1] if len(gen_output_tokens_list) > 1 else 0,
                "gen1_prompt": gen_prompts[1] if len(gen_prompts) > 1 else None,
                "gen1_full_output": gen_outputs[1] if len(gen_outputs) > 1 else None,
                "EM_after_reflection1": ems[1] if len(ems) > 1 else None,
                "EM2_after_reflection1": em2s[1] if len(em2s) > 1 else None,
                "BLEU_after_reflection1": bleus[1] if len(bleus) > 1 else None,
                "CodeBLEU_after_reflection1": cbleus[1] if len(cbleus) > 1 else None,
                "ROUGE-L_after_reflection1": rouges[1] if len(rouges) > 1 else None,
                "Edit_Progress_after_reflection1": edit_progresses[1] if len(edit_progresses) > 1 else None,
                "reflection2_time": reflection_times[1] if len(reflection_times) > 1 else 0.0,
                "reflection2_input_tokens": reflection_input_tokens_list[1] if len(
                    reflection_input_tokens_list) > 1 else 0,
                "reflection2_output_tokens": reflection_output_tokens_list[1] if len(
                    reflection_output_tokens_list) > 1 else 0,
                "reflection2_prompt": reflection_prompts[1] if len(reflection_prompts) > 1 else None,
                "reflection2_full_output": reflection_outputs[1] if len(reflection_outputs) > 1 else None,

                # 第二次反思后的指标（对应gen2的输出）
                "gen2_time": gen_times[2] if len(gen_times) > 2 else 0.0,
                "gen2_input_tokens": gen_input_tokens_list[2] if len(gen_input_tokens_list) > 2 else 0,
                "gen2_output_tokens": gen_output_tokens_list[2] if len(gen_output_tokens_list) > 2 else 0,
                "gen2_prompt": gen_prompts[2] if len(gen_prompts) > 2 else None,
                "gen2_full_output": gen_outputs[2] if len(gen_outputs) > 2 else None,
                "EM_after_reflection2": ems[2] if len(ems) > 2 else None,
                "EM2_after_reflection2": em2s[2] if len(em2s) > 2 else None,
                "BLEU_after_reflection2": bleus[2] if len(bleus) > 2 else None,
                "CodeBLEU_after_reflection2": cbleus[2] if len(cbleus) > 2 else None,
                "ROUGE-L_after_reflection2": rouges[2] if len(rouges) > 2 else None,
                "Edit_Progress_after_reflection2": edit_progresses[2] if len(edit_progresses) > 2 else None,
                "reflection3_time": reflection_times[2] if len(reflection_times) > 2 else 0.0,
                "reflection3_input_tokens": reflection_input_tokens_list[2] if len(
                    reflection_input_tokens_list) > 2 else 0,
                "reflection3_output_tokens": reflection_output_tokens_list[2] if len(
                    reflection_output_tokens_list) > 2 else 0,
                "reflection3_prompt": reflection_prompts[2] if len(reflection_prompts) > 2 else None,
                "reflection3_full_output": reflection_outputs[2] if len(reflection_outputs) > 2 else None,

                # 第三次反思后的指标（对应gen3的输出）
                "gen3_time": gen_times[3] if len(gen_times) > 3 else 0.0,
                "gen3_input_tokens": gen_input_tokens_list[3] if len(gen_input_tokens_list) > 3 else 0,
                "gen3_output_tokens": gen_output_tokens_list[3] if len(gen_output_tokens_list) > 3 else 0,
                "gen3_prompt": gen_prompts[3] if len(gen_prompts) > 3 else None,
                "gen3_full_output": gen_outputs[3] if len(gen_outputs) > 3 else None,
                "EM_after_reflection3": ems[3] if len(ems) > 3 else None,
                "EM2_after_reflection3": em2s[3] if len(em2s) > 3 else None,
                "BLEU_after_reflection3": bleus[3] if len(bleus) > 3 else None,
                "CodeBLEU_after_reflection3": cbleus[3] if len(cbleus) > 3 else None,
                "ROUGE-L_after_reflection3": rouges[3] if len(rouges) > 3 else None,
                "Edit_Progress_after_reflection3": edit_progresses[3] if len(edit_progresses) > 3 else None,

                # 经验总结和更新
                "summarize_time": summarize_time if 'summarize_time' in locals() else 0.0,
                "summarize_input_tokens": summarize_input_tokens if 'summarize_input_tokens' in locals() else 0,
                "summarize_output_tokens": summarize_output_tokens if 'summarize_output_tokens' in locals() else 0,
                "summarize_prompt": summarize_prompt if 'summarize_prompt' in locals() else None,
                "summarize_full_output": summarize_full_output if 'summarize_full_output' in locals() else None,
                "update_gen_time": update_gen_time if 'update_gen_time' in locals() else 0.0,
                "update_rhe_time": update_rhe_time if 'update_rhe_time' in locals() else 0.0,
                "update_exp_input_tokens": update_exp_input_tokens if 'update_exp_input_tokens' in locals() else 0,
                "update_exp_output_tokens": update_exp_output_tokens if 'update_exp_output_tokens' in locals() else 0,
                "update_prompts": update_prompts if 'update_prompts' in locals() else None,
                "update_outputs": update_outputs if 'update_outputs' in locals() else None,
                "save_exp_time": save_exp_time if 'save_exp_time' in locals() else 0.0,
            }
            save_xlsx_append(RESULT_XLSX, row)
            results.append(row)
            processed_repo_pr_code.add((repo, before_code))

        if results:
            em_h = np.mean([r["EM_hre"] for r in results])
            em2_h = np.mean([r["EM2_hre"] for r in results])
            bleu_h = np.mean([r["BLEU_hre"] for r in results])
            cbleu_h = np.mean([r["CodeBLEU_hre"] for r in results])
            rouge_h = np.mean([r["ROUGE-L_hre"] for r in results])
            edit_progress_h = np.mean([r["Edit_Progress_hre"] for r in results])
            avg_processing_time = np.mean([r["Processing_Time_Seconds"] for r in results])

            # 计算每个步骤的平均时间和token
            avg_search_time = np.mean([r.get("search_time", 0) for r in results])
            avg_gen0_time = np.mean([r.get("gen0_time", 0) for r in results])
            avg_gen0_input_tokens = np.mean([r.get("gen0_input_tokens", 0) for r in results])
            avg_gen0_output_tokens = np.mean([r.get("gen0_output_tokens", 0) for r in results])
            avg_reflection1_time = np.mean([r.get("reflection1_time", 0) for r in results])
            avg_reflection1_input_tokens = np.mean([r.get("reflection1_input_tokens", 0) for r in results])
            avg_reflection1_output_tokens = np.mean([r.get("reflection1_output_tokens", 0) for r in results])
            avg_gen1_time = np.mean([r.get("gen1_time", 0) for r in results])
            avg_gen1_input_tokens = np.mean([r.get("gen1_input_tokens", 0) for r in results])
            avg_gen1_output_tokens = np.mean([r.get("gen1_output_tokens", 0) for r in results])
            avg_reflection2_time = np.mean([r.get("reflection2_time", 0) for r in results])
            avg_reflection2_input_tokens = np.mean([r.get("reflection2_input_tokens", 0) for r in results])
            avg_reflection2_output_tokens = np.mean([r.get("reflection2_output_tokens", 0) for r in results])
            avg_gen2_time = np.mean([r.get("gen2_time", 0) for r in results])
            avg_gen2_input_tokens = np.mean([r.get("gen2_input_tokens", 0) for r in results])
            avg_gen2_output_tokens = np.mean([r.get("gen2_output_tokens", 0) for r in results])
            avg_reflection3_time = np.mean([r.get("reflection3_time", 0) for r in results])
            avg_reflection3_input_tokens = np.mean([r.get("reflection3_input_tokens", 0) for r in results])
            avg_reflection3_output_tokens = np.mean([r.get("reflection3_output_tokens", 0) for r in results])
            avg_gen3_time = np.mean([r.get("gen3_time", 0) for r in results])
            avg_gen3_input_tokens = np.mean([r.get("gen3_input_tokens", 0) for r in results])
            avg_gen3_output_tokens = np.mean([r.get("gen3_output_tokens", 0) for r in results])
            avg_summarize_time = np.mean([r.get("summarize_time", 0) for r in results])
            avg_summarize_input_tokens = np.mean([r.get("summarize_input_tokens", 0) for r in results])
            avg_summarize_output_tokens = np.mean([r.get("summarize_output_tokens", 0) for r in results])
            avg_update_gen_time = np.mean([r.get("update_gen_time", 0) for r in results])
            avg_update_rhe_time = np.mean([r.get("update_rhe_time", 0) for r in results])
            avg_update_exp_input_tokens = np.mean([r.get("update_exp_input_tokens", 0) for r in results])
            avg_update_exp_output_tokens = np.mean([r.get("update_exp_output_tokens", 0) for r in results])
            avg_save_exp_time = np.mean([r.get("save_exp_time", 0) for r in results])

            ensure_dir(METRIC_FILE)
            with open(METRIC_FILE, "w", encoding="utf-8") as f:
                f.write("=== RQ2 HRE Evaluation ===\n")
                f.write(
                    f"With HRE   EM={em_h:.4f} EM2={em2_h:.4f} BLEU={bleu_h:.4f} CodeBLEU={cbleu_h:.4f} ROUGE-L={rouge_h:.4f} Edit_Progress={edit_progress_h:.4f}, avg_processing_time={avg_processing_time:.4f} seconds\n")
                f.write("\n=== Average Time and Token Statistics ===\n")
                f.write(f"Search Time: {avg_search_time:.4f} seconds\n")
                f.write(
                    f"Gen0 Time: {avg_gen0_time:.4f} seconds, Input Tokens: {avg_gen0_input_tokens:.0f}, Output Tokens: {avg_gen0_output_tokens:.0f}\n")
                f.write(
                    f"Reflection1 Time: {avg_reflection1_time:.4f} seconds, Input Tokens: {avg_reflection1_input_tokens:.0f}, Output Tokens: {avg_reflection1_output_tokens:.0f}\n")
                f.write(
                    f"Gen1 Time: {avg_gen1_time:.4f} seconds, Input Tokens: {avg_gen1_input_tokens:.0f}, Output Tokens: {avg_gen1_output_tokens:.0f}\n")
                f.write(
                    f"Reflection2 Time: {avg_reflection2_time:.4f} seconds, Input Tokens: {avg_reflection2_input_tokens:.0f}, Output Tokens: {avg_reflection2_output_tokens:.0f}\n")
                f.write(
                    f"Gen2 Time: {avg_gen2_time:.4f} seconds, Input Tokens: {avg_gen2_input_tokens:.0f}, Output Tokens: {avg_gen2_output_tokens:.0f}\n")
                f.write(
                    f"Reflection3 Time: {avg_reflection3_time:.4f} seconds, Input Tokens: {avg_reflection3_input_tokens:.0f}, Output Tokens: {avg_reflection3_output_tokens:.0f}\n")
                f.write(
                    f"Gen3 Time: {avg_gen3_time:.4f} seconds, Input Tokens: {avg_gen3_input_tokens:.0f}, Output Tokens: {avg_gen3_output_tokens:.0f}\n")
                f.write(
                    f"Summarize Time: {avg_summarize_time:.4f} seconds, Input Tokens: {avg_summarize_input_tokens:.0f}, Output Tokens: {avg_summarize_output_tokens:.0f}\n")
                f.write(
                    f"Update Gen Time: {avg_update_gen_time:.4f} seconds, Input Tokens: {avg_update_exp_input_tokens:.0f}, Output Tokens: {avg_update_exp_output_tokens:.0f}\n")
                f.write(f"Update RHE Time: {avg_update_rhe_time:.4f} seconds\n")
                f.write(f"Save Exp Time: {avg_save_exp_time:.4f} seconds\n")
            print("      评估完成，结果写入：", METRIC_FILE)
            print(f"     平均每条数据处理时间：{avg_processing_time:.4f} 秒")
        else:
            print("      无可评估样本。")
