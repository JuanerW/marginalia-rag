from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate


class RagChainError(RuntimeError):
    pass


SYSTEM_PROMPT = """你是一个无剧透的小说阅读助手。只根据提供的已读原文回答。
不得使用未提供的剧情或你自己的小说知识。
答案中的事实必须使用 [1]、[2] 形式引用证据编号。
如果证据不足，明确回答“当前已读内容中没有足够信息”。"""

RAG_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("human", "问题：{question}\n\n已读原文：\n{context}"),
    ]
)


def build_rag_chain(model: BaseChatModel):
    return RAG_PROMPT | model | StrOutputParser()


def sanitize_model_output(content: str) -> str:
    answer = content.strip()
    if "</think>" in answer:
        answer = answer.rsplit("</think>", 1)[-1].strip()
    if not answer:
        raise RagChainError("模型没有返回最终答案")
    return answer


async def answer_with_langchain(
    model: BaseChatModel,
    question: str,
    context: str,
) -> str:
    try:
        content = await build_rag_chain(model).ainvoke(
            {"question": question, "context": context}
        )
    except Exception as exc:  # LangChain providers expose different exception types.
        raise RagChainError(f"LLM 请求失败：{exc}") from exc
    return sanitize_model_output(content)
