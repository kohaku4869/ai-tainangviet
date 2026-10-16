"""Kiểm tra pipeline không cần LLM: code viết tay -> executor -> formatter -> so với đáp án."""
import csv, json, sys
sys.path.insert(0, ".")
from xlqa.solvers import get_blocks
from xlqa.executor import run_code
from xlqa.formatting import format_answer

ORACLE = {
"p4_q001": "a=(df['F']-df['E']); answer=df.loc[a.sort_values().index[1],'D']",
"p4_q002": "a=(df['F']-df['E']); answer=df.loc[a.sort_values(ascending=False).index[1],'G']",
"p4_q003": "answer=df.sort_values('E',ascending=False).head(10)['G'].max()",
"p4_q004": "answer='Yes' if df.loc[4,'G']>df.loc[4,'F'] else 'No'",
"p4_q005": "d=df.dropna(subset=['H']); answer=d.loc[d['H'].abs().idxmax(),'B']",
"p4_q006": "answer=abs(df.loc[25,'E']-df.loc[26,'E'])",
"p4_q007": "answer=df.loc[31,list('BCDEFGHI')].mean()",
"p4_q008": "c=list('BCDEFGHIJKLM'); answer=df.loc[11,c].sum()-df.loc[9,c].sum()",
"p4_q009": "answer=df.loc[11,'C']+df.loc[11,'D']",
"p4_q010": "c=list('BCDEFGHIJKLM'); import re; k=df.loc[9,c].astype(float).idxmax(); answer=['Mining','Construction','Manufacturing','Wholesale and retail trade','Transportation and utilities','Information','Financial activities','Professional and business services','Education and health services','Leisure and hospitality','Other services','Public administration'][c.index(k)]",
"p4_q011": "answer='Yes' if df.loc[10,'H']>df.loc[10,'F'] else 'No'",
"p4_q012": "answer=df.loc[7,'E']",
"p4_q013": "s={'Agriculture':df.loc[9,'M'],'Manufacturing':df.loc[12,'M'],'Construction':df.loc[11,'M']}; answer=sorted(s,key=s.get,reverse=True)",
"p4_q014": "answer=df.loc[12,'E']+df.loc[12,'F']",
"p4_q015": "answer=df.loc[8,'C']",
"p4_q016": "d=df.drop(5).dropna(subset=['F']); answer=d.loc[d['F'].idxmax(),'A']",
"p4_q017": "answer=abs(df.loc[11,'B']-df.loc[10,'B'])",
"p4_q018": "answer=[df.loc[10,'C'],df.loc[10,'G']]",
"p4_q019": "answer=[df.loc[57,'H'],df.loc[61,'H']]",
"p4_q020": "answer=df.loc[10,'B']",
}
qs = json.load(open("data/queries.json", encoding="utf-8"))
gold = {r["id"]: r["answer"] for r in csv.DictReader(open("data/sample_submission.csv", encoding="utf-8-sig"))}
ok = 0
for q in qs:
    blocks = list(get_blocks(f"data/xlsx_files/{q['file_name']}"))
    v, err, _ = run_code(ORACLE[q["id"]], blocks)
    a = format_answer(v, q["query"]) if not err else f"ERR {err}"
    good = a == gold[q["id"]]; ok += good
    print("OK " if good else "BAD", q["id"], repr(a), "" if good else f"gold={gold[q['id']]!r}")
print(f"{ok}/{len(qs)}")
