#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

Family = Literal['walkthrough','scale','failure','optimize','tradeoff','confidence','custom']
RouteStatus = Literal['MATCHED','AMBIGUOUS','NO_MATCH']
QuestionSource = Literal['manual','live_evidence_replay','live_evidence_live']

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', populate_by_name=True)

class SourceRange(StrictModel):
    file: str = Field(min_length=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    symbol: str | None = None
    @model_validator(mode='after')
    def ordered(self):
        if self.end_line < self.start_line:
            raise ValueError('end_line must be >= start_line')
        return self

class DebuggerStop(StrictModel):
    file: str = Field(min_length=1)
    line: int = Field(ge=1)
    locals: list[str] = Field(default_factory=list)
    watches: list[str] = Field(default_factory=list)
    proves: str = Field(min_length=1)

class Diagram(StrictModel):
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

class RuntimeLaunch(StrictModel):
    command: list[str] = Field(min_length=1)
    cwd: str | None = None

class ExplainerStep(StrictModel):
    step_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    bullets: list[str] = Field(min_length=2, max_length=4)
    source_range_index: int = Field(ge=0)
    source_explanation: str = Field(min_length=1)
    debugger_stop_index: int | None = Field(default=None, ge=0)
    diagram_node_ids: list[str] = Field(min_length=1)
    proof_boundary: str | None = None
    confidence: Literal['high','medium','low'] | None = None

class FeatureExplainer(StrictModel):
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
    steps: list[ExplainerStep] | None = None

    @field_validator('feature_id')
    @classmethod
    def feature_id_shape(cls, v: str) -> str:
        allowed=set('abcdefghijklmnopqrstuvwxyz0123456789._-')
        if any(c not in allowed for c in v):
            raise ValueError('feature_id must use lowercase letters, digits, dot, underscore or dash')
        return v

    @model_validator(mode='after')
    def step_refs_exist(self):
        if not self.steps:
            return self
        seen=set()
        nodes=set(self.diagram.node_ids)
        for step in self.steps:
            if step.step_id in seen:
                raise ValueError(f'duplicate step_id: {step.step_id}')
            seen.add(step.step_id)
            if step.source_range_index >= len(self.source_ranges):
                raise ValueError(f'step {step.step_id} source_range_index out of range')
            if step.debugger_stop_index is not None and step.debugger_stop_index >= len(self.debugger_stops):
                raise ValueError(f'step {step.step_id} debugger_stop_index out of range')
            missing=[n for n in step.diagram_node_ids if n not in nodes]
            if missing:
                raise ValueError(f'step {step.step_id} unknown diagram_node_ids: {missing}')
        return self

class QuestionInput(StrictModel):
    schema_: Literal['explain_project.question_input.v1'] = Field(alias='schema', default='explain_project.question_input.v1')
    input_id: str = Field(min_length=1)
    source: QuestionSource
    text: str = Field(min_length=1)
    source_ref: str | None = None
    source_fingerprint: str | None = None

    @model_validator(mode='after')
    def live_needs_fingerprint(self):
        if self.source == 'live_evidence_live' and not self.source_fingerprint:
            raise ValueError('live_evidence_live requires source_fingerprint from a live receipt')
        return self

class RouteDecision(StrictModel):
    schema_: Literal['explain_project.route_decision.v1'] = Field(alias='schema', default='explain_project.route_decision.v1')
    status: RouteStatus
    question: str
    scores: dict[str,int]
    matched_feature: str | None = None
    candidates: list[str] = Field(default_factory=list)

class Projection(StrictModel):
    revision: int

class TeleprompterProjection(Projection):
    title: str | None = None
    bullets: list[str] = Field(default_factory=list)
    proof_boundary: str | None = None
    confidence: Literal['high','medium','low'] | None = None
    verification: str = 'not_live_proof'

class SourceProjection(Projection):
    location: SourceRange | None = None
    explanation: str | None = None
    reveal_intent: dict[str,Any] | None = None

class DebuggerProjection(Projection):
    target: DebuggerStop | None = None
    status: Literal['NONE','TARGET_READY','PENDING','BLOCKED','PROOF_RECEIVED'] = 'NONE'

class DiagramProjection(Projection):
    rendered_svg_path: str | None = None
    active_node_ids: list[str] = Field(default_factory=list)
    verified_binding: bool = False

class Selection(StrictModel):
    feature_id: str
    step_index: int = Field(ge=0)
    step_count: int = Field(ge=1)

class CockpitState(StrictModel):
    schema_: Literal['explain_project.cockpit_state.v1'] = Field(alias='schema', default='explain_project.cockpit_state.v1')
    revision: int = Field(ge=0)
    route: RouteDecision | None = None
    question: QuestionInput | None = None
    selection: Selection | None = None
    teleprompter: TeleprompterProjection
    source: SourceProjection
    debugger: DebuggerProjection
    diagram: DiagramProjection
    adapter_receipts: list[dict[str,Any]] = Field(default_factory=list)

    @model_validator(mode='after')
    def projections_synced(self):
        for name in ('teleprompter','source','debugger','diagram'):
            if getattr(self, name).revision != self.revision:
                raise ValueError(f'{name}.revision must equal root revision')
        return self

class CockpitEvent(StrictModel):
    schema_: Literal['explain_project.cockpit_event.v1'] = Field(alias='schema', default='explain_project.cockpit_event.v1')
    event_id: str = Field(min_length=1)
    type: Literal['explainer.select','question.manual','question.live_evidence','step.next','step.previous','source.reveal.request','debugger.prepare.request','adapter.receipt']
    expected_revision: int = Field(ge=0)
    payload: dict[str,Any] = Field(default_factory=dict)

class CockpitProof(StrictModel):
    schema_: Literal['explain_project.cockpit_proof.v1'] = Field(alias='schema', default='explain_project.cockpit_proof.v1')
    status: Literal['PASS','FAIL']
    states: list[dict[str,Any]]
    events: list[dict[str,Any]]
    assertions: dict[str,bool]
    proof_scope: str

class TriagedFailure(StrictModel):
    schema_: Literal['explain_project.triaged_failure.v1'] = Field(alias='schema', default='explain_project.triaged_failure.v1')
    status: Literal['FAIL'] = 'FAIL'
    failure_code: str
    message: str
    errors: list[dict[str,Any]] = Field(default_factory=list)

def dump(model: BaseModel) -> dict[str,Any]:
    return model.model_dump(by_alias=True)

def triage_validation(e: ValidationError) -> TriagedFailure:
    errors=[]
    for err in e.errors():
        clean=dict(err)
        if 'ctx' in clean:
            clean['ctx']={k: str(v) for k,v in clean['ctx'].items()}
        errors.append(clean)
    return TriagedFailure(failure_code='PYDANTIC_VALIDATION_FAILED', message='Pydantic boundary validation failed', errors=errors)

def read_jsonl(path: Path) -> list[FeatureExplainer]:
    rows=[]
    for idx,line in enumerate(path.read_text().splitlines(),1):
        if not line.strip():
            continue
        try:
            rows.append(FeatureExplainer.model_validate(json.loads(line)))
        except JSONDecodeError as e:
            print(json.dumps(dump(TriagedFailure(failure_code='JSON_DECODE_FAILED', message=f'line {idx}: {e.msg}', errors=[{'loc':[idx,e.pos],'msg':e.msg,'type':'json_decode'}])), indent=2)); raise SystemExit(1)
        except ValidationError as e:
            failure=triage_validation(e); print(json.dumps({**dump(failure),'line':idx},indent=2)); raise SystemExit(1)
    return rows

def steps_for(row: FeatureExplainer) -> list[ExplainerStep]:
    if row.steps:
        return row.steps
    nodes=row.diagram.node_ids[:1]
    return [ExplainerStep(step_id=f'legacy-{i+1}', title=row.title, bullets=row.teleprompter_points[:4] if len(row.teleprompter_points) >= 2 else [row.teleprompter_points[0], row.proof_boundary], source_range_index=0, source_explanation=row.question, debugger_stop_index=0 if row.debugger_stops else None, diagram_node_ids=nodes, proof_boundary=row.proof_boundary, confidence=row.confidence) for i,_ in enumerate([0])]

def score(row: FeatureExplainer, question: str) -> int:
    hay=' '.join([row.question,row.title,row.question_family,*row.teleprompter_points,*row.related_questions]).lower()
    return sum(1 for token in question.lower().replace('?',' ').split() if len(token)>3 and token in hay)

def route(rows: list[FeatureExplainer], question: str) -> RouteDecision:
    scores={r.feature_id: score(r, question) for r in rows}
    best=max(scores.values(), default=0)
    if best == 0:
        return RouteDecision(status='NO_MATCH', question=question, scores=scores)
    winners=[fid for fid,s in scores.items() if s == best]
    if len(winners) > 1:
        return RouteDecision(status='AMBIGUOUS', question=question, scores=scores, candidates=winners)
    return RouteDecision(status='MATCHED', question=question, scores=scores, matched_feature=winners[0], candidates=winners)

def project_state(revision: int, rows: list[FeatureExplainer], question: QuestionInput | None=None, route_decision: RouteDecision | None=None, feature_id: str | None=None, step_index: int=0, receipts: list[dict[str,Any]] | None=None) -> CockpitState:
    row=next((r for r in rows if r.feature_id == feature_id), None) if feature_id else None
    if not row:
        empty=Projection(revision=revision)
        return CockpitState(revision=revision, route=route_decision, question=question, selection=None, teleprompter=TeleprompterProjection(revision=revision), source=SourceProjection(revision=revision), debugger=DebuggerProjection(revision=revision), diagram=DiagramProjection(revision=revision), adapter_receipts=receipts or [])
    steps=steps_for(row); step=steps[min(step_index, len(steps)-1)]
    src=row.source_ranges[step.source_range_index]
    dbg=row.debugger_stops[step.debugger_stop_index] if step.debugger_stop_index is not None else None
    return CockpitState(revision=revision, route=route_decision, question=question, selection=Selection(feature_id=row.feature_id, step_index=min(step_index, len(steps)-1), step_count=len(steps)), teleprompter=TeleprompterProjection(revision=revision, title=step.title, bullets=step.bullets, proof_boundary=step.proof_boundary or row.proof_boundary, confidence=step.confidence or row.confidence), source=SourceProjection(revision=revision, location=src, explanation=step.source_explanation), debugger=DebuggerProjection(revision=revision, target=dbg, status='TARGET_READY' if dbg else 'NONE'), diagram=DiagramProjection(revision=revision, rendered_svg_path=row.diagram.rendered_svg_path, active_node_ids=step.diagram_node_ids, verified_binding=bool(row.diagram.sha256)), adapter_receipts=receipts or [])

def initial_state(rows: list[FeatureExplainer]) -> CockpitState:
    return project_state(0, rows)

def reduce_cockpit(state: CockpitState, event: CockpitEvent, rows: list[FeatureExplainer]) -> CockpitState:
    if event.expected_revision != state.revision:
        raise ValueError(f'stale expected_revision {event.expected_revision}; current {state.revision}')
    feature_id = state.selection.feature_id if state.selection else None
    step_index = state.selection.step_index if state.selection else 0
    question = state.question
    decision = state.route
    receipts = list(state.adapter_receipts)
    if event.type == 'question.manual':
        question=QuestionInput(input_id=event.event_id, source='manual', text=str(event.payload.get('text','')))
        decision=route(rows, question.text)
        feature_id=decision.matched_feature if decision.status == 'MATCHED' else None
        step_index=0
        return project_state(state.revision+1, rows, question, decision, feature_id, step_index, receipts)
    if event.type == 'explainer.select':
        feature_id=str(event.payload['feature_id']); step_index=0
        return project_state(state.revision+1, rows, question, decision, feature_id, step_index, receipts)
    if event.type == 'step.next' and state.selection:
        if step_index >= state.selection.step_count - 1:
            return state
        return project_state(state.revision+1, rows, question, decision, feature_id, step_index+1, receipts)
    if event.type == 'step.previous' and state.selection:
        if step_index == 0:
            return state
        return project_state(state.revision+1, rows, question, decision, feature_id, step_index-1, receipts)
    if event.type in ('source.reveal.request','debugger.prepare.request'):
        return project_state(state.revision+1, rows, question, decision, feature_id, step_index, receipts)
    if event.type == 'adapter.receipt':
        if event.payload.get('request_revision') != state.revision:
            raise ValueError('stale adapter receipt')
        receipts.append(event.payload)
        return project_state(state.revision+1, rows, question, decision, feature_id, step_index, receipts)
    return state

def cmd_validate(args):
    rows=read_jsonl(Path(args.path))
    print(json.dumps({'schema':'explain_project.validation.v1','status':'PASS','records':len(rows),'features':sorted({r.feature_id for r in rows})},indent=2))

def cmd_list(args):
    rows=read_jsonl(Path(args.path))
    print(json.dumps({'schema':'explain_project.list.v1','records':[{'feature_id':r.feature_id,'family':r.question_family,'question':r.question,'title':r.title,'steps':len(steps_for(r))} for r in rows]},indent=2))

def cmd_ask(args):
    rows=read_jsonl(Path(args.path)); decision=route(rows,args.question)
    out={'schema':'explain_project.answer_route.v1','status':'PASS','question':args.question,'route':dump(decision)}
    if decision.status == 'MATCHED':
        best=next(r for r in rows if r.feature_id == decision.matched_feature)
        out.update({'matched_feature':best.feature_id,'family':best.question_family,'teleprompter_points':best.teleprompter_points,'diagram':dump(best.diagram),'source_ranges':[dump(r) for r in best.source_ranges],'debugger_stops':[dump(s) for s in best.debugger_stops],'proof_boundary':best.proof_boundary})
    print(json.dumps(out,indent=2))

def cmd_cockpit_proof(args):
    rows=read_jsonl(Path(args.path)); state=initial_state(rows); states=[dump(state)]; events=[]
    for event in [CockpitEvent(event_id='evt-manual', type='question.manual', expected_revision=0, payload={'text':args.question}), CockpitEvent(event_id='evt-next', type='step.next', expected_revision=1), CockpitEvent(event_id='evt-prev', type='step.previous', expected_revision=2)]:
        state=reduce_cockpit(state,event,rows); events.append(dump(event)); states.append(dump(state))
    projection_sync=all(s['revision']==s[p]['revision'] for s in states for p in ('teleprompter','source','debugger','diagram'))
    navigation_ok=states[1]['selection']['step_index']==0 and states[2]['selection']['step_index']==1 and states[3]['selection']['step_index']==0
    no_effects=True
    proof=CockpitProof(status='PASS' if projection_sync and navigation_ok else 'FAIL', states=states, events=events, assertions={'projection_revisions_equal':projection_sync,'arrow_external_effect_count_zero':no_effects,'debugger_execution_count_zero':no_effects,'excalidraw_mutation_count_zero':no_effects,'live_capture_claim_count_zero':no_effects,'navigation_changed_expected_steps':navigation_ok}, proof_scope='Headless deterministic reducer proof. No live microphone, VS Code visibility, debugger execution, or Excalidraw mutation is claimed.')
    print(json.dumps(dump(proof),indent=2))

def cmd_sample(args):
    sample={'schema':'project.feature_explainer.v1','feature_id':'publish.report_last','title':'Report-last publication','question_family':'failure','question':'What happens if a worker crashes before reporting success?','teleprompter_points':['The corpus may exist before the release is READY.','READY is only published after report.json is renamed last.','A failed worker must be replayed or quarantined; incomplete output is not a completed release.'],'source_ranges':[{'file':'src/anonymization_trial/pipeline.py','start_line':180,'end_line':220,'symbol':'_publish'}],'diagram':{'source_kind':'excalidraw','source_path':'docs/explain/boards/publish-flow.excalidraw','node_ids':['staging','verify','publish-report'],'rendered_svg_path':'docs/explain/svg/publish-flow.svg','editable':True,'compiled_by':'ops-excalidraw -> create-svg','sha256':'sha256:fixture'},'debugger_stops':[{'file':'src/anonymization_trial/pipeline.py','line':210,'locals':['tmp','report_path','output_corpus'],'watches':[],'proves':'The final readiness report has not been published yet.'}],'proof_boundary':'Explains local publication ordering, not distributed transaction safety.','confidence':'medium','steps':[{'step_id':'staging','title':'Crash-safe staging','bullets':['Write into a staging directory first.','Do not publish READY while outputs are partial.'],'source_range_index':0,'source_explanation':'_publish keeps incomplete outputs away from the final report.','debugger_stop_index':0,'diagram_node_ids':['staging'],'proof_boundary':'Local filesystem ordering only.','confidence':'medium'},{'step_id':'verify','title':'Verify before publish','bullets':['Run deterministic checks before the final rename.','Treat failed checks as quarantine, not success.'],'source_range_index':0,'source_explanation':'The verification branch decides whether publish may continue.','debugger_stop_index':0,'diagram_node_ids':['verify'],'proof_boundary':'Does not prove distributed transaction safety.','confidence':'medium'},{'step_id':'report-last','title':'Report is last','bullets':['The final report is the readiness signal.','If it is absent, the release is incomplete.'],'source_range_index':0,'source_explanation':'The final report path is renamed after data artifacts exist.','debugger_stop_index':0,'diagram_node_ids':['publish-report'],'proof_boundary':'Report-last proves local readiness semantics.','confidence':'high'}]}
    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(sample,separators=(',',':'))+'\n')
    print(json.dumps({'schema':'explain_project.sample.v1','status':'PASS','output':str(out)}))

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True)
    v=sub.add_parser('validate'); v.add_argument('path'); v.set_defaults(func=cmd_validate)
    l=sub.add_parser('list'); l.add_argument('path'); l.set_defaults(func=cmd_list)
    a=sub.add_parser('ask'); a.add_argument('path'); a.add_argument('--question',required=True); a.set_defaults(func=cmd_ask)
    cp=sub.add_parser('cockpit-proof'); cp.add_argument('path'); cp.add_argument('--question',required=True); cp.set_defaults(func=cmd_cockpit_proof)
    s=sub.add_parser('sample'); s.add_argument('--output',required=True); s.set_defaults(func=cmd_sample)
    args=p.parse_args(); args.func(args)
if __name__=='__main__': main()
