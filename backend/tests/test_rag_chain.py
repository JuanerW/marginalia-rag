import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from src.services.rag_chain import answer_with_langchain


@pytest.mark.asyncio
async def test_rag_chain_formats_prompt_and_removes_reasoning() -> None:
    model = FakeListChatModel(
        responses=["<think>internal reasoning</think>\n张角创立了太平道。[1]"]
    )

    answer = await answer_with_langchain(
        model,
        "张角是谁？",
        "[1] 第一回\n张角创立太平道。",
    )

    assert answer == "张角创立了太平道。[1]"
