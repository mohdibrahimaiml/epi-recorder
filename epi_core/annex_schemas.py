from __future__ import annotations
from typing import Any, Optional, Literal
from pydantic import BaseModel, Field, model_validator

class BiasAnalysis(BaseModel):
    demographic_parity_diff: Optional[float] = None
    equal_opportunity_diff: Optional[float] = None
    disparate_impact_ratio: Optional[float] = None
    analysis_date: Optional[str] = None
    mitigations_applied: list[str] = Field(default_factory=list)

class PreprocessingStep(BaseModel):
    step: str
    method: str
    params: dict[str, Any] = Field(default_factory=dict)

class DatasetDatasheet(BaseModel):
    dataset_name: str
    version: str = '1.0.0'
    dataset_type: Literal['training','validation','test']
    collection_date: Optional[str] = None
    jurisdiction: Optional[str] = None
    provenance: dict[str, Any] = Field(default_factory=lambda: {'source':'','collection_method':''})
    num_samples: Optional[int] = None
    num_features: Optional[int] = None
    feature_types: dict[str, int] = Field(default_factory=dict)
    class_distribution: Optional[dict[str, float]] = None
    sensitive_attributes: list[str] = Field(default_factory=list)
    bias_analysis: Optional[BiasAnalysis] = None
    preprocessing: list[PreprocessingStep] = Field(default_factory=list)
    exclusion_criteria: list[str] = Field(default_factory=list)
    governance: dict[str, Any] = Field(default_factory=lambda: {'retention_policy':'','data_controller':'','sensitive_data_handling':''})
    status: Literal['draft','complete','approved'] = 'draft'
    last_modified: Optional[str] = None

class ApprovalStamp(BaseModel):
    signed_by: Optional[str] = None
    signed_at: Optional[str] = None
    signature: Optional[str] = None
    notes: Optional[str] = None

class ComponentSpec(BaseModel):
    component: str
    version: str
    description: str
    input_schema: Optional[str] = None
    output_schema: Optional[str] = None
    dependencies: list[str] = Field(default_factory=list)

class DesignDecision(BaseModel):
    id: str
    decision: str
    rationale: str
    date: Optional[str] = None
    approved_by: Optional[str] = None

class SystemDescription(BaseModel):
    system_name: str = ""
    version: str = ""
    workflow_id: Optional[str] = None
    goal: Optional[str] = None
    intended_purpose: str = ""
    deployment_context: Optional[str] = None
    users: list[str] = Field(default_factory=list)
    scope_limitations: Optional[str] = None
    provider_name: Optional[str] = None
    provider_contact: Optional[str] = None

class DesignAndDevelopment(BaseModel):
    architecture_summary: Optional[str] = None
    architecture_diagram_ref: Optional[str] = None
    component_specifications: list[ComponentSpec] = Field(default_factory=list)
    development_methodology: Optional[str] = None
    design_tools: list[str] = Field(default_factory=list)
    design_decisions: list[DesignDecision] = Field(default_factory=list)

class RiskManagementSummary(BaseModel):
    methodology: str = 'ISO 14971 / EU AI Act Article 9'
    risk_register_ref: Optional[str] = None
    overall_residual_risk: Literal['acceptable','acceptable_with_monitoring','unacceptable'] = 'acceptable_with_monitoring'
    risk_review_date: Optional[str] = None
    risk_officer: Optional[str] = None

class Section01System(BaseModel):
    meta: dict[str, Any] = Field(default_factory=lambda: {'section':'1','title':'System Description','status':'draft','version':'1.0.0'})
    system_description: SystemDescription = Field(default_factory=SystemDescription)
    design_and_development: DesignAndDevelopment = Field(default_factory=DesignAndDevelopment)
    risk_management_summary: RiskManagementSummary = Field(default_factory=RiskManagementSummary)
    approval: ApprovalStamp = Field(default_factory=ApprovalStamp)

class ArchitectureDescription(BaseModel):
    system_architecture: Optional[str] = None
    algorithm_summary: Optional[str] = None
    key_design_choices: list[DesignDecision] = Field(default_factory=list)
    computational_resources: Optional[str] = None
    data_requirements: Optional[str] = None
    training_methodology: Optional[str] = None

class HumanOversightMeasures(BaseModel):
    oversight_strategy: Optional[str] = None
    human_in_the_loop: Optional[str] = None
    override_mechanisms: Optional[str] = None
    escalation_path: Optional[str] = None

class PredeterminedChanges(BaseModel):
    change_id: str
    description: str
    trigger_condition: Optional[str] = None
    expected_impact: Optional[str] = None
    validation_required: bool = True

class ValidationAndTesting(BaseModel):
    methodology: Optional[str] = None
    test_logs_ref: Optional[str] = None
    accuracy_metrics: dict[str, Any] = Field(default_factory=dict)
    robustness_metrics: dict[str, Any] = Field(default_factory=dict)
    discriminatory_impact_analysis: Optional[str] = None
    test_reports: list[dict[str, Any]] = Field(default_factory=list)
    responsible_persons: list[str] = Field(default_factory=list)

class CybersecurityMeasures(BaseModel):
    measures: list[str] = Field(default_factory=list)
    standards_applied: list[str] = Field(default_factory=list)
    last_assessment_date: Optional[str] = None

class Section02Development(BaseModel):
    meta: dict[str, Any] = Field(default_factory=lambda: {'section':'2','title':'Development Process','status':'draft','version':'1.0.0'})
    architecture: ArchitectureDescription = Field(default_factory=ArchitectureDescription)
    datasheets: list[DatasetDatasheet] = Field(default_factory=list)
    human_oversight: HumanOversightMeasures = Field(default_factory=HumanOversightMeasures)
    predetermined_changes: list[PredeterminedChanges] = Field(default_factory=list)
    validation_testing: ValidationAndTesting = Field(default_factory=ValidationAndTesting)
    cybersecurity: CybersecurityMeasures = Field(default_factory=CybersecurityMeasures)
    approval: ApprovalStamp = Field(default_factory=ApprovalStamp)

class SubgroupAccuracy(BaseModel):
    group: str; metric: str; value: float; sample_size: int

class Section03Monitoring(BaseModel):
    meta: dict[str, Any] = Field(default_factory=lambda: {'section':'3','title':'Monitoring','status':'draft','version':'1.0.0'})
    capabilities_and_limitations: Optional[str] = None
    subgroup_accuracy: list[SubgroupAccuracy] = Field(default_factory=list)
    unintended_outcomes: list[str] = Field(default_factory=list)
    human_oversight_measures: Optional[str] = None
    input_data_specifications: Optional[str] = None
    runtime_logging_ref: Optional[str] = 'steps.jsonl'
    approval: ApprovalStamp = Field(default_factory=ApprovalStamp)

class MetricJustification(BaseModel):
    metric: str; value: Optional[float] = None; justification: str; limitations: Optional[str] = None

class Section04Metrics(BaseModel):
    meta: dict[str, Any] = Field(default_factory=lambda: {'section':'4','title':'Metrics','status':'draft','version':'1.0.0'})
    metrics: list[MetricJustification] = Field(default_factory=list)
    overall_rationale: Optional[str] = None
    approval: ApprovalStamp = Field(default_factory=ApprovalStamp)

class RiskEntry(BaseModel):
    id: str
    risk_description: str
    category: Literal['health','safety','fundamental_rights','discrimination','cybersecurity','operational']
    probability: int = Field(ge=1, le=5)
    severity: int = Field(ge=1, le=5)
    rpn_score: Optional[int] = None
    risk_level: Optional[Literal['low','medium','high','critical']] = None
    controls: list[str] = Field(default_factory=list)
    residual_probability: Optional[int] = Field(default=None, ge=1, le=5)
    residual_severity: Optional[int] = Field(default=None, ge=1, le=5)
    residual_rpn: Optional[int] = None
    residual_risk_level: Optional[Literal['low','medium','high','critical']] = None
    risk_treatment: Literal['mitigation','avoidance','transfer','acceptance'] = 'mitigation'
    risk_owner: Optional[str] = None
    sign_off: Optional[ApprovalStamp] = None
    @model_validator(mode='after')
    def _compute_rpn(self) -> 'RiskEntry':
        if self.rpn_score is None:
            self.rpn_score = self.probability * self.severity
        if self.risk_level is None:
            s = self.rpn_score
            if s >= 16: self.risk_level = 'critical'
            elif s >= 10: self.risk_level = 'high'
            elif s >= 5: self.risk_level = 'medium'
            else: self.risk_level = 'low'
        rp = self.residual_probability
        rs = self.residual_severity
        if rp is not None and rs is not None:
            if self.residual_rpn is None: self.residual_rpn = rp * rs
            if self.residual_risk_level is None:
                s = self.residual_rpn
                if s >= 16: self.residual_risk_level = 'critical'
                elif s >= 10: self.residual_risk_level = 'high'
                elif s >= 5: self.residual_risk_level = 'medium'
                else: self.residual_risk_level = 'low'
        return self

class OverallRiskAssessment(BaseModel):
    highest_rpn: Optional[int] = None
    mean_rpn: Optional[float] = None
    risks_above_threshold: int = 0
    residual_risks_above_threshold: int = 0
    assessment_date: Optional[str] = None
    conclusion: Optional[str] = None

class Section05RiskManagement(BaseModel):
    meta: dict[str, Any] = Field(default_factory=lambda: {'section':'5','title':'Risk Management','methodology':'ISO14971','version':'1.0.0','status':'draft'})
    risk_register: list[RiskEntry] = Field(default_factory=list)
    overall_assessment: OverallRiskAssessment = Field(default_factory=OverallRiskAssessment)
    approval: ApprovalStamp = Field(default_factory=ApprovalStamp)

class ChangeLogEntry(BaseModel):
    change_id: str; date: str; description: str
    type: Literal['minor','substantial']
    trigger: Optional[str] = None
    re_certification_required: bool = False
    approved_by: Optional[str] = None

class Section06Lifecycle(BaseModel):
    meta: dict[str, Any] = Field(default_factory=lambda: {'section':'6','title':'Lifecycle Changes','status':'draft','version':'1.0.0'})
    changes: list[ChangeLogEntry] = Field(default_factory=list)
    change_classification_matrix: Optional[str] = None
    approval: ApprovalStamp = Field(default_factory=ApprovalStamp)

class HarmonisedStandard(BaseModel):
    standard_id: str; title: str
    status: Literal['applied','partial','under_review','not_applied']
    scope: Optional[str] = None
    conformity_assessment: Literal['self-declaration','notified-body'] = 'self-declaration'
    citations: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    remediation_plan: Optional[dict[str, Any]] = None

class Section07Standards(BaseModel):
    meta: dict[str, Any] = Field(default_factory=lambda: {'section':'7','title':'Standards','status':'draft','version':'1.0.0'})
    harmonised_standards: list[HarmonisedStandard] = Field(default_factory=list)
    other_applicable_standards: list[dict[str, Any]] = Field(default_factory=list)
    approval: ApprovalStamp = Field(default_factory=ApprovalStamp)

class ManufacturerInfo(BaseModel):
    name: str = ""; address: Optional[str] = None
    contact: Optional[str] = None
    registration_number: Optional[str] = None

class Signatory(BaseModel):
    name: str = ""; role: str = ""
    organisation: Optional[str] = None
    did: Optional[str] = None

class Section08Declaration(BaseModel):
    meta: dict[str, Any] = Field(default_factory=lambda: {'section':'8','title':'EU DoC','status':'draft','version':'1.0.0','type':'EU Declaration of Conformity'})
    regulation: str = 'Regulation (EU) 2024/1689'
    annex_ref: str = 'IV'
    manufacturer: ManufacturerInfo = Field(default_factory=ManufacturerInfo)
    system_name: str = ''; system_version: str = ''
    system_type: Optional[str] = None
    notified_body: Optional[str] = None
    declares_under_sole_responsibility: str = ''
    applied_standards: list[str] = Field(default_factory=list)
    ce_marking_year: Optional[str] = None
    declaration_date: Optional[str] = None
    signatory: Signatory = Field(default_factory=Signatory)
    signature: Optional[str] = None

class Section09PostMarket(BaseModel):
    meta: dict[str, Any] = Field(default_factory=lambda: {'section':'9','title':'Post-Market','status':'draft','version':'1.0.0'})
    monitoring_scope: Optional[str] = None
    drift_detection_thresholds: dict[str, Any] = Field(default_factory=dict)
    subgroup_monitoring_schedule: Optional[str] = None
    human_override_rate_tracking: bool = False
    cross_system_interaction_monitoring: bool = False
    serious_incident_definition: Optional[str] = None
    escalation_runbook: Optional[str] = None
    reporting_deadlines: dict[str, str] = Field(default_factory=lambda: {'critical':'<=2days','severe':'<=10days','general':'<=15days'})
    feedback_loop_to_technical_file: bool = False
    approval: ApprovalStamp = Field(default_factory=ApprovalStamp)

class SectionSummary(BaseModel):
    section: str; title: str
    status: Literal['missing','draft','complete','approved']
    fields_populated: int = 0
    fields_total: int = 0
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None

class AnnexComplianceSummary(BaseModel):
    system_name: str = ''; system_version: str = ''
    generated_at: str = ''
    container_hash: Optional[str] = None
    sections: list[SectionSummary] = Field(default_factory=list)
    overall_completion_pct: float = 0.0
    approved_sections: int = 0
    total_sections: int = 9

class AnnexIVTechnicalFile(BaseModel):
    meta: dict[str, Any] = Field(default_factory=lambda: {'schema':'EU AI Act Annex IV','schema_version':'1.0.0','generated_at':'','generated_by':'epi annex compile'})
    section_01: Section01System = Field(default_factory=Section01System)
    section_02: Section02Development = Field(default_factory=Section02Development)
    section_03: Section03Monitoring = Field(default_factory=Section03Monitoring)
    section_04: Section04Metrics = Field(default_factory=Section04Metrics)
    section_05: Section05RiskManagement = Field(default_factory=Section05RiskManagement)
    section_06: Section06Lifecycle = Field(default_factory=Section06Lifecycle)
    section_07: Section07Standards = Field(default_factory=Section07Standards)
    section_08: Section08Declaration = Field(default_factory=Section08Declaration)
    section_09: Section09PostMarket = Field(default_factory=Section09PostMarket)
    datasheets: list[DatasetDatasheet] = Field(default_factory=list)
    compliance_summary: Optional[AnnexComplianceSummary] = None
