#!/usr/bin/env python3
"""
Interview integration for collaborative persona creation.

Uses /interview skill to gather persona details interactively,
enabling human-agent collaboration on persona modeling.
"""

import json
import tempfile
from pathlib import Path
from typing import Optional

from .persona import Persona, run_skill
from .templates import get_template, get_interview_questions, get_default_bridges

from loguru import logger as log


def run_interview(
    questions: list[dict],
    title: str = "Persona Creation",
    context: str = "",
    timeout: int = 300,
) -> dict:
    """Run /interview skill to ask questions.

    Args:
        questions: List of question dicts with id, text, header, options
        title: Title for the interview form
        context: Additional context for the interview
        timeout: Timeout in seconds

    Returns:
        Dict mapping question id to selected answer(s)
    """
    interview_data = {
        "title": title,
        "context": context or "Help me create a persona by answering these questions.",
        "questions": questions,
    }

    # Write questions to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(interview_data, f, indent=2)
        questions_file = f.name

    try:
        result = run_skill("interview", ["--mode", "tui", "--file", questions_file], timeout=timeout)

        if result["returncode"] == 0:
            # Parse response
            try:
                response = json.loads(result["stdout"])
                if response and "answers" in response:
                    return response["answers"]
            except json.JSONDecodeError:
                # Try to parse line by line for simpler output
                answers = {}
                for line in result["stdout"].split("\n"):
                    if ":" in line:
                        parts = line.split(":", 1)
                        if len(parts) == 2:
                            answers[parts[0].strip()] = parts[1].strip()
                if answers:
                    return answers

        log.warning("Interview failed or timed out: %s", result.get("stderr", "")[:100])
        return {}

    finally:
        Path(questions_file).unlink(missing_ok=True)


def interview_for_persona(
    name: str,
    template_name: str = "client",
    additional_questions: Optional[list[dict]] = None,
) -> dict:
    """Run interactive interview to gather persona details.

    Args:
        name: Name of the persona being created
        template_name: Template to use for questions
        additional_questions: Extra questions to ask

    Returns:
        Dict of gathered persona attributes
    """
    # Get template questions
    questions = get_interview_questions(template_name)

    # Add any additional questions
    if additional_questions:
        questions.extend(additional_questions)

    if not questions:
        log.warning("No interview questions for template '%s'", template_name)
        return {}

    # Run interview
    title = f"Creating {template_name.title()} Persona: {name}"
    context = f"Let's gather details about {name} to create a useful persona model."

    answers = run_interview(questions, title=title, context=context)

    if not answers:
        log.warning("Interview returned no answers")
        return {}

    # Map answers to persona attributes
    attributes = _map_answers_to_attributes(answers, template_name)

    log.info("Interview gathered %d attributes for persona '%s'", len(attributes), name)
    return attributes


def _map_answers_to_attributes(answers: dict, template_name: str) -> dict:
    """Map interview answers to Persona attributes.

    Args:
        answers: Raw answers from interview
        template_name: Template for context

    Returns:
        Dict of Persona-compatible attributes
    """
    attributes = {}

    # Role mapping
    if "role" in answers:
        role_answer = answers["role"]
        if "Executive" in role_answer:
            attributes["role"] = "Executive"
            attributes["communication_style"] = "direct"
        elif "Director" in role_answer or "Manager" in role_answer:
            attributes["role"] = "Manager"
            attributes["communication_style"] = "diplomatic"
        elif "Individual" in role_answer or "IC" in role_answer:
            attributes["role"] = "Individual Contributor"
            attributes["communication_style"] = "technical"
        elif "Consultant" in role_answer:
            attributes["role"] = "Consultant"
            attributes["communication_style"] = "business-focused"
        else:
            attributes["role"] = role_answer

    # Priority → Goals
    if "priority" in answers:
        priority = answers["priority"]
        goals = []
        if "Cost" in priority:
            goals.append("Reduce costs")
        if "Speed" in priority:
            goals.append("Deliver quickly")
        if "Quality" in priority:
            goals.append("Ensure quality and reliability")
        if "Innovation" in priority:
            goals.append("Implement innovative solutions")
        if goals:
            attributes["goals"] = goals
        else:
            attributes["goals"] = [priority]

    # Concerns
    if "concerns" in answers:
        concerns_answer = answers["concerns"]
        concerns = []
        if isinstance(concerns_answer, list):
            for c in concerns_answer:
                concerns.append(c)
        elif isinstance(concerns_answer, str):
            # Parse comma-separated or multi-select
            for c in concerns_answer.replace(", ", ",").split(","):
                c = c.strip()
                if "Security" in c or "compliance" in c.lower():
                    concerns.append("Security and compliance requirements")
                elif "Scalability" in c:
                    concerns.append("System scalability")
                elif "Integration" in c:
                    concerns.append("Integration with existing systems")
                elif "Maintenance" in c:
                    concerns.append("Long-term maintenance")
                elif c:
                    concerns.append(c)
        if concerns:
            attributes["concerns"] = concerns

    # Communication style
    if "communication" in answers:
        comm = answers["communication"]
        if "Direct" in comm or "concise" in comm.lower():
            attributes["communication_style"] = "direct"
            attributes["preferred_format"] = "bullet points"
        elif "Detailed" in comm:
            attributes["communication_style"] = "thorough"
            attributes["preferred_format"] = "detailed prose"
        elif "Visual" in comm:
            attributes["communication_style"] = "visual"
            attributes["preferred_format"] = "diagrams"
        elif "Data" in comm:
            attributes["communication_style"] = "data-driven"
            attributes["preferred_format"] = "metrics and charts"

    # Domain (expert template)
    if "domain" in answers:
        domain = answers["domain"]
        if "Science" in domain or "Research" in domain:
            attributes["domain"] = "research"
        elif "Technology" in domain or "Engineering" in domain:
            attributes["domain"] = "technology"
        elif "Business" in domain or "Strategy" in domain:
            attributes["domain"] = "business"
        elif "Creative" in domain or "Design" in domain:
            attributes["domain"] = "creative"
        else:
            attributes["domain"] = domain.lower()

    # Expertise depth (expert template)
    if "expertise_depth" in answers:
        depth = answers["expertise_depth"]
        if "Deep" in depth:
            attributes["_learn_depth"] = "deep"
        elif "Standard" in depth:
            attributes["_learn_depth"] = "standard"
        else:
            attributes["_learn_depth"] = "quick"

    # Known for → Expertise
    if "known_for" in answers:
        known_for = answers["known_for"]
        expertise = []
        if isinstance(known_for, list):
            expertise = known_for
        elif isinstance(known_for, str):
            expertise = [k.strip() for k in known_for.split(",")]
        if expertise:
            attributes["expertise"] = expertise

    # Influence (stakeholder template)
    if "influence" in answers:
        influence = answers["influence"]
        if "Decision maker" in influence:
            attributes["tags"] = attributes.get("tags", []) + ["decision-maker"]
        elif "Strong influencer" in influence:
            attributes["tags"] = attributes.get("tags", []) + ["influencer"]

    # Working style
    if "working_style" in answers:
        style = answers["working_style"]
        if "Async" in style or "written" in style.lower():
            attributes["preferred_format"] = "documents"
        elif "Sync" in style or "meetings" in style.lower():
            attributes["preferred_format"] = "meetings"
        elif "Hands-on" in style or "pairing" in style.lower():
            attributes["preferred_format"] = "collaborative sessions"

    # Adversary template mappings
    if "actor_type" in answers:
        actor = answers["actor_type"]
        if "Nation-state" in actor or "APT" in actor:
            attributes["tags"] = attributes.get("tags", []) + ["apt", "nation-state"]
            attributes["expertise"] = ["advanced persistent threats", "espionage"]
        elif "Cybercriminal" in actor:
            attributes["tags"] = attributes.get("tags", []) + ["cybercrime"]
            attributes["goals"] = ["Financial gain"]
        elif "Insider" in actor:
            attributes["tags"] = attributes.get("tags", []) + ["insider-threat"]
        elif "Hacktivist" in actor:
            attributes["tags"] = attributes.get("tags", []) + ["hacktivist"]
            attributes["goals"] = ["Ideological objectives"]

    if "capability" in answers:
        cap = answers["capability"]
        if "Advanced" in cap:
            attributes["expertise"] = attributes.get("expertise", []) + ["zero-days", "custom tooling"]
        elif "Basic" in cap:
            attributes["constraints"] = ["Limited to commodity tools"]

    if "objectives" in answers:
        objectives = answers["objectives"]
        goals = attributes.get("goals", [])
        if isinstance(objectives, str):
            objectives = [o.strip() for o in objectives.split(",")]
        for obj in objectives:
            if "Data" in obj or "exfiltration" in obj.lower():
                goals.append("Data exfiltration")
            elif "Persistence" in obj:
                goals.append("Maintain persistent access")
            elif "Disruption" in obj:
                goals.append("Disrupt operations")
            elif "Financial" in obj or "Ransomware" in obj.lower():
                goals.append("Financial gain")
        if goals:
            attributes["goals"] = list(set(goals))

    if "ttp" in answers:
        ttps = answers["ttp"]
        expertise = attributes.get("expertise", [])
        if isinstance(ttps, str):
            ttps = [t.strip() for t in ttps.split(",")]
        for ttp in ttps:
            if "Phishing" in ttp or "social" in ttp.lower():
                expertise.append("social engineering")
            elif "Supply chain" in ttp:
                expertise.append("supply chain attacks")
            elif "Credential" in ttp:
                expertise.append("credential theft")
            elif "Vulnerability" in ttp:
                expertise.append("vulnerability exploitation")
        if expertise:
            attributes["expertise"] = list(set(expertise))

    return attributes


def create_persona_interactively(
    name: str,
    template_name: str = "client",
    scope: Optional[str] = None,
    organization: Optional[str] = None,
) -> Optional[Persona]:
    """Create a persona through interactive interview.

    Args:
        name: Name of the persona
        template_name: Template to use
        scope: Memory scope (default: template default)
        organization: Optional organization name

    Returns:
        Created Persona if successful, None otherwise
    """
    from .templates import get_template, get_default_scope, get_default_bridges

    template = get_template(template_name)
    if not template:
        log.error("Unknown template: %s", template_name)
        return None

    # Get scope
    if scope is None:
        scope = get_default_scope(template_name)

    # Run interview
    print(f"\n  Creating {template_name} persona: {name}")
    print(f"  Template: {template.get('description', '')}")
    print()

    attributes = interview_for_persona(name, template_name)

    if not attributes:
        print("  Interview cancelled or failed")
        return None

    # Create persona with gathered attributes
    persona = Persona(
        name=name,
        template=template_name,
        scope=scope,
        organization=organization or "",
        tags=template.get("tags", []),
        bridge_weights=get_default_bridges(template_name),
        **{k: v for k, v in attributes.items() if not k.startswith("_")},
    )

    # Store the learning depth for /ask learn
    learn_depth = attributes.get("_learn_depth", "quick")

    print(f"\n  Persona created: {name}")
    print(f"    Role: {persona.role or '(not set)'}")
    print(f"    Domain: {persona.domain or '(not set)'}")
    print(f"    Goals: {len(persona.goals)} defined")
    print(f"    Concerns: {len(persona.concerns)} defined")

    return persona, learn_depth
