# agent.py

import os
from typing import List, TypedDict
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
from prompt_template import SYSTEM_PROMPT

load_dotenv()

class AgentState(TypedDict):
    messages: List[AnyMessage]
    is_emergency: bool

class TriageAgent:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.5)
        self.graph = self._build_graph()

    def _build_graph(self):
        graph_builder = StateGraph(AgentState)
        graph_builder.add_node("llm_call", self.call_llm)
        graph_builder.add_node("emergency_check", self.check_for_emergency)
        graph_builder.set_entry_point("emergency_check")
        graph_builder.add_edge("llm_call", END)
        graph_builder.add_conditional_edges(
            "emergency_check",
            self.route_after_emergency_check,
            {"emergency": END, "continue": "llm_call"}
        )
        return graph_builder.compile()

    def call_llm(self, state: AgentState):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        response = self.llm.invoke(messages)
        return {"messages": [response]}

    def check_for_emergency(self, state: AgentState):
        last_user_message = state["messages"][-1].content.lower()
        emergency_keywords = [
            "dor no peito", "aperto no peito", "falta de ar", "dificuldade para respirar",
            "desmaio", "perda de consciência", "sangramento intenso", "hemorragia",
            "confusão mental", "fraqueza súbita", "dificuldade para falar", "convulsão", "suicídio"
        ]
        is_emergency = any(keyword in last_user_message for keyword in emergency_keywords)
        if is_emergency:
            emergency_response = AIMessage(
                content="Entendi. Com base no que você descreveu, seus sintomas podem indicar uma situação que precisa de atenção imediata. Por favor, procure o pronto-socorro mais próximo ou ligue para o SAMU (192) agora mesmo. Não podemos continuar a triagem por aqui para sua segurança."
            )
            return {"messages": [emergency_response], "is_emergency": True}
        return {"is_emergency": False}

    def route_after_emergency_check(self, state: AgentState):
        if state.get("is_emergency"):
            return "emergency"
        return "continue"

    def run(self, messages: List[AnyMessage]):
        final_state = self.graph.invoke({"messages": messages})
        return final_state['messages'][-1]