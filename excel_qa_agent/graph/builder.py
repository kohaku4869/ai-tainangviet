"""Xây dựng graph LangGraph.

    START ─┬─> load_workbook ─┐
           └─> parse_format  ─┴─> dispatch ─(bảng nhỏ, cấu trúc rõ)─> fast_solver ─(đồng thuận)─> finalize ─> END
                                     │                                  └─(không chắc)─┐
                                     └─(lớn / bất thường)──────────────────> agent <─> execute_code ─> finalize
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from excel_qa_agent.nodes import (
    agent,
    dispatch,
    execute_code,
    fast_solver,
    finalize,
    load_workbook,
    parse_format,
    route_after_agent,
    route_after_execute,
    route_after_fast,
    route_after_load,
)
from excel_qa_agent.graph.state import AgentState, InputState, OutputState


def build_graph():
    builder = StateGraph(AgentState, input_schema=InputState, output_schema=OutputState)
    builder.add_node("load_workbook", load_workbook)
    builder.add_node("parse_format", parse_format)
    builder.add_node("dispatch", dispatch)
    builder.add_node("fast_solver", fast_solver)
    builder.add_node("agent", agent)
    builder.add_node("execute_code", execute_code)
    builder.add_node("finalize", finalize)

    # load_workbook và parse_format chạy song song, hội tụ ở dispatch rồi mới chọn đường.
    builder.add_edge(START, "load_workbook")
    builder.add_edge(START, "parse_format")
    builder.add_edge(["load_workbook", "parse_format"], "dispatch")
    builder.add_conditional_edges("dispatch", route_after_load, ["fast_solver", "agent"])
    builder.add_conditional_edges("fast_solver", route_after_fast, ["finalize", "agent"])
    builder.add_conditional_edges("agent", route_after_agent, ["execute_code", "finalize"])
    builder.add_conditional_edges("execute_code", route_after_execute, ["agent", "finalize"])
    builder.add_edge("finalize", END)
    return builder.compile(name="excel_qa_agent")


graph = build_graph()
