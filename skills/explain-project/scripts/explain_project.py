#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from json import JSONDecodeError
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

Family = Literal['walkthrough','scale','failure','optimize','tradeoff','confidence','custom']

class SourceRange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    file: str = Field(min_length=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    symbol: str | None = None
    @model_validator(mode='after')
    def ordered(self):
        if self.end_line < self.start_line:
            raise ValueError('end_line must be >= start_line')
        return self

class DebuggerStop(BaseModel):
    model_config = ConfigDict(extra='forbid')
    file: str = Field(min_length=1)
    line: int = Field(ge=1)
    locals: list[str] = Field(default_factory=list)
    watches: list[str] = Field(default_factory=list)
    proves: str = Field(min_length=1)

class Diagram(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_kind: Literal['excalidraw','svg'] = 'excalidraw'
    source_path: str = Field(min_length=1)
    node_ids: list[str] = Field(min_length=1)
    rendered_svg_path: str | None = None
    editable: bool = True
    compiled_by: str | None = None
    sha256: str | None = None
    @model_validator(mode='after')
    def diagram_boundary(self):
        if self.source_kind == 'excalidraw' and not self.editable:
            raise ValueError('excalidraw diagram source must be editable')
        return self

class RuntimeLaunch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    command: list[str] = Field(min_length=1)
    cwd: str | None = None

class FeatureExplainer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_: Literal['project.feature_explainer.v1'] = Field(alias='schema')
    feature_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    question_family: Family
    question: str = Field(min_length=1)
    teleprompter_points: list[str] = Field(min_length=1)
    source_ranges: list[SourceRange] = Field(min_length=1)
    diagram: Diagram
    proof_boundary: str = Field(min_length=1)
    debugger_stops: list[DebuggerStop] = Field(default_factory=list)
    runtime_launch: RuntimeLaunch | None = None
    related_questions: list[str] = Field(default_factory=list)
    confidence: Literal['high','medium','low'] = 'medium'
    last_verified: str | None = None
    @field_validator('feature_id')
    @classmethod
    def feature_id_shape(cls, v: str) -> str:
        allowed=set('abcdefghijklmnopqrstuvwxyz0123456789._-')
        if any(c not in allowed for c in v):
            raise ValueError('feature_id must use lowercase letters, digits, dot, underscore or dash')
        return v


def read_jsonl(path: Path) -> list[FeatureExplainer]:
    rows=[]
    for idx,line in enumerate(path.read_text().splitlines(),1):
        if not line.strip():
            continue
        try:
            data=json.loads(line)
            rows.append(FeatureExplainer.model_validate(data))
        except JSONDecodeError as e:
            print(json.dumps({'schema':'explain_project.validation.v1','status':'FAIL','line':idx,'errors':[{'type':'json_decode','loc':[idx,e.pos],'msg':e.msg}]},indent=2))
            raise SystemExit(1)
        except ValidationError as e:
            print(json.dumps({'schema':'explain_project.validation.v1','status':'FAIL','line':idx,'errors':e.errors()},indent=2))
            raise SystemExit(1)
    return rows

def cmd_validate(args):
    rows=read_jsonl(Path(args.path))
    print(json.dumps({'schema':'explain_project.validation.v1','status':'PASS','records':len(rows),'features':sorted({r.feature_id for r in rows})},indent=2))

def cmd_list(args):
    rows=read_jsonl(Path(args.path))
    print(json.dumps({'schema':'explain_project.list.v1','records':[{'feature_id':r.feature_id,'family':r.question_family,'question':r.question,'title':r.title} for r in rows]},indent=2))

def score(row: FeatureExplainer, question: str) -> int:
    hay=' '.join([row.question,row.title,row.question_family,*row.teleprompter_points,*row.related_questions]).lower()
    return sum(1 for token in question.lower().replace('?',' ').split() if len(token)>3 and token in hay)

def cmd_ask(args):
    rows=read_jsonl(Path(args.path))
    best=max(rows, key=lambda r: score(r,args.question))
    print(json.dumps({'schema':'explain_project.answer_route.v1','status':'PASS','question':args.question,'matched_feature':best.feature_id,'family':best.question_family,'teleprompter_points':best.teleprompter_points,'diagram':best.diagram.model_dump(),'source_ranges':[r.model_dump() for r in best.source_ranges],'debugger_stops':[s.model_dump() for s in best.debugger_stops],'proof_boundary':best.proof_boundary},indent=2))

def cmd_sample(args):
    sample={
        'schema':'project.feature_explainer.v1','feature_id':'publish.report_last','title':'Report-last publication','question_family':'failure','question':'What happens if a worker crashes before reporting success?','teleprompter_points':['The corpus may exist before the release is READY.','READY is only published after report.json is renamed last.','A failed worker must be replayed or quarantined; incomplete output is not a completed release.'],'source_ranges':[{'file':'src/anonymization_trial/pipeline.py','start_line':180,'end_line':220,'symbol':'_publish'}],'diagram':{'source_kind':'excalidraw','source_path':'docs/explain/boards/publish-flow.excalidraw','node_ids':['staging','verify','publish-report'],'rendered_svg_path':'docs/explain/svg/publish-flow.svg','editable':True,'compiled_by':'ops-excalidraw -> create-svg'},'debugger_stops':[{'file':'src/anonymization_trial/pipeline.py','line':210,'locals':['tmp','report_path','output_corpus'],'proves':'The final readiness report has not been published yet.'}],'proof_boundary':'Explains local publication ordering, not distributed transaction safety.','confidence':'medium'}
    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(sample,separators=(',',':'))+'\n')
    print(json.dumps({'schema':'explain_project.sample.v1','status':'PASS','output':str(out)}))

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest='cmd',required=True)
    v=sub.add_parser('validate'); v.add_argument('path'); v.set_defaults(func=cmd_validate)
    l=sub.add_parser('list'); l.add_argument('path'); l.set_defaults(func=cmd_list)
    a=sub.add_parser('ask'); a.add_argument('path'); a.add_argument('--question',required=True); a.set_defaults(func=cmd_ask)
    s=sub.add_parser('sample'); s.add_argument('--output',required=True); s.set_defaults(func=cmd_sample)
    args=p.parse_args(); args.func(args)
if __name__=='__main__': main()
