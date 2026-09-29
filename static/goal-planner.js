/**
 * GOAP-style goal planner ported from Ruflo's v3/goal_ui/src/lib/goapPlanner.ts.
 * Vanilla JS, no external dependencies, Hermes WebUI-native.
 */

(function(){
  const DEFAULT_STATE = {
    goalDefined: false,
    goalParsed: false,
    stateAssessed: false,
    informationGathered: false,
    documentsAnalyzed: false,
    knowledgeSynthesized: false,
    insightsGenerated: false,
    verified: false,
  };

  function parseGoal(goal){
    const lower = String(goal || '').toLowerCase();
    let domain = 'general';
    if (lower.includes('quantum') || lower.includes('computing')) domain = 'technology';
    if (lower.includes('market') || lower.includes('business')) domain = 'business';
    if (lower.includes('architecture') || lower.includes('software') || lower.includes('code')) domain = 'software engineering';
    if (lower.includes('energy') || lower.includes('renewable')) domain = 'energy';
    if (lower.includes('security') || lower.includes('soc') || lower.includes('cyber') || lower.includes('ssh') || lower.includes('firewall') || lower.includes('malware') || lower.includes('phishing') || lower.includes('intrusion')) domain = 'cybersecurity';

    let action = 'research';
    if (lower.includes('analyze')) action = 'analyze';
    if (lower.includes('investigate')) action = 'investigate';
    if (lower.includes('compare')) action = 'compare';
    if (lower.includes('evaluate')) action = 'evaluate';
    if (lower.includes('build') || lower.includes('implement')) action = 'build';

    const keywords = String(goal || '').split(/\s+/).filter(w => w.length > 4).slice(0, 5);
    return { domain, action, keywords };
  }

  function defaultActions(){
    return [
      { name: 'analyzeGoal', cost: 1, preconditions: { goalDefined: true }, effects: { goalParsed: true },
        title: 'Goal Analysis', icon: 'target',
        description: (goal, meta) => `Analyze "${goal.slice(0,60)}..." and break it down into actionable sub-goals for ${meta.domain}.`,
        data: (goal) => [
          { text: 'Parse objective', details: { objective: 'Extract and structure the high-level goal from natural language input.', effects: ['Structured goal object created','Sub-goals identified'], agents: ['Planner Agent'] } },
          { text: 'Identify dependencies', details: { objective: 'Map relationships between actions and their requirements.', effects: ['Dependency graph generated','Critical path identified'], agents: ['Dependency Analyzer'] } },
          { text: 'Map state transitions', details: { objective: 'Define how each action transforms the world state.', effects: ['Transition matrix created','State reachability confirmed'], agents: ['State Mapper'] } },
        ] },
      { name: 'assessState', cost: 1, preconditions: { goalParsed: true }, effects: { stateAssessed: true },
        title: 'State Assessment', icon: 'brain',
        description: (goal, meta) => `Evaluate current knowledge about ${meta.domain} and identify information gaps before ${meta.action}.`,
        data: () => [
          { text: 'Assess current state', details: { objective: 'Evaluate available knowledge and capability baseline.', effects: ['Baseline established','Gaps identified'], agents: ['State Assessor'] } },
          { text: 'Define success criteria', details: { objective: 'Establish measurable outcomes that indicate the goal is met.', effects: ['Success criteria documented','Validation plan created'], agents: ['Criteria Agent'] } },
          { text: 'Estimate cost and priority', details: { objective: 'Score actions by effort, risk, and value.', effects: ['Priority ranking created','Resource estimate ready'], agents: ['Estimator Agent'] } },
        ] },
      { name: 'gatherInformation', cost: 2, preconditions: { stateAssessed: true }, effects: { informationGathered: true },
        title: 'Information Gathering', icon: 'search',
        description: (goal, meta) => `Collect sources, run searches, and interview repositories for ${meta.keywords.join(', ')}.`,
        data: (goal, meta) => [
          { text: 'Run targeted searches', details: { objective: `Find current references for ${meta.keywords.join(', ')}.`, effects: ['Raw sources collected','Citation list started'], agents: ['Research Agent'] } },
          { text: 'Read relevant documents', details: { objective: 'Ingest and summarize the most relevant sources.', effects: ['Document summaries ready','Key quotes extracted'], agents: ['Reader Agent'] } },
          { text: 'Validate source quality', details: { objective: 'Score sources for authority, recency, and bias.', effects: ['Quality scores assigned','Low-confidence sources flagged'], agents: ['Verifier Agent'] } },
        ] },
      { name: 'analyzeDocuments', cost: 2, preconditions: { informationGathered: true }, effects: { documentsAnalyzed: true },
        title: 'Document Analysis', icon: 'file-search',
        description: () => `Extract findings, methodologies, and actionable insights from gathered sources.`,
        data: () => [
          { text: 'Extract key findings', details: { objective: 'Identify the most important facts and claims.', effects: ['Findings catalogued'], agents: ['Extractor Agent'] } },
          { text: 'Cross-reference sources', details: { objective: 'Find agreements, conflicts, and gaps across sources.', effects: ['Conflict map created'], agents: ['Synthesizer Agent'] } },
          { text: 'Assess confidence', details: { objective: 'Assign confidence levels based on evidence quality.', effects: ['Confidence matrix ready'], agents: ['Reviewer Agent'] } },
        ] },
      { name: 'synthesizeKnowledge', cost: 2, preconditions: { documentsAnalyzed: true }, effects: { knowledgeSynthesized: true },
        title: 'Knowledge Synthesis', icon: 'git-branch',
        description: () => `Weave findings into a coherent picture and identify practical recommendations.`,
        data: () => [
          { text: 'Build narrative', details: { objective: 'Connect findings into a readable, evidence-based story.', effects: ['Narrative draft complete'], agents: ['Writer Agent'] } },
          { text: 'Generate recommendations', details: { objective: 'Turn findings into concrete next actions.', effects: ['Recommendation list created'], agents: ['Advisor Agent'] } },
          { text: 'Trace to sources', details: { objective: 'Link every claim back to supporting evidence.', effects: ['Citation map complete'], agents: ['Citation Agent'] } },
        ] },
      { name: 'generateInsights', cost: 2, preconditions: { knowledgeSynthesized: true }, effects: { insightsGenerated: true },
        title: 'Insight Generation', icon: 'lightbulb',
        description: () => `Produce novel insights, risk flags, and strategic options from the synthesized work.`,
        data: () => [
          { text: 'Identify patterns', details: { objective: 'Spot recurring themes and outliers.', effects: ['Pattern list generated'], agents: ['Pattern Agent'] } },
          { text: 'Surface risks', details: { objective: 'Highlight assumptions, gaps, and failure modes.', effects: ['Risk register created'], agents: ['Risk Agent'] } },
          { text: 'Draft options', details: { objective: 'Create decision options with trade-offs.', effects: ['Option cards ready'], agents: ['Strategy Agent'] } },
        ] },
      { name: 'verify', cost: 1, preconditions: { insightsGenerated: true }, effects: { verified: true },
        title: 'Verification', icon: 'check-circle',
        description: () => `Re-check the plan against success criteria and produce a final, actionable summary.`,
        data: () => [
          { text: 'Validate against criteria', details: { objective: 'Confirm success criteria are met.', effects: ['Completion checklist signed off'], agents: ['Validator Agent'] } },
          { text: 'Package deliverables', details: { objective: 'Format outputs for the user and downstream tools.', effects: ['Deliverables ready'], agents: ['Publisher Agent'] } },
        ] },
    ];
  }

  function heuristic(state, goal){
    let distance = 0;
    for (const key in goal) {
      if (goal[key] && !state[key]) distance++;
    }
    return distance;
  }

  function preconditionsMet(state, preconditions){
    for (const key in preconditions) {
      if (preconditions[key] && !state[key]) return false;
    }
    return true;
  }

  function applyEffects(state, effects){
    return { ...state, ...effects };
  }

  function plan(goal, options = {}){
    const { currentState = {}, goalState = {}, actions = null } = options;
    const meta = parseGoal(goal);
    const initialState = { ...DEFAULT_STATE, goalDefined: true, ...currentState };
    const targetState = { ...DEFAULT_STATE, verified: true, ...goalState };
    const actionList = actions || defaultActions();

    const openList = [ { state: initialState, actions: [], cost: 0, heuristic: heuristic(initialState, targetState) } ];
    const closedList = new Set();

    while (openList.length > 0){
      openList.sort((a, b) => (a.cost + a.heuristic) - (b.cost + b.heuristic));
      const current = openList.shift();
      const stateKey = JSON.stringify(current.state);

      if (heuristic(current.state, targetState) === 0){
        return {
          goal,
          meta,
          steps: current.actions.map((action, index) => ({
            id: String(index + 1),
            name: action.name,
            title: action.title,
            icon: action.icon,
            status: 'pending',
            description: action.description(goal, meta),
            data: action.data(goal, meta),
            cost: action.cost,
          })),
        };
      }

      if (closedList.has(stateKey)) continue;
      closedList.add(stateKey);

      for (const action of actionList){
        if (preconditionsMet(current.state, action.preconditions)){
          const newState = applyEffects(current.state, action.effects);
          const newStateKey = JSON.stringify(newState);
          if (!closedList.has(newStateKey)){
            openList.push({
              state: newState,
              actions: [...current.actions, action],
              cost: current.cost + action.cost,
              heuristic: heuristic(newState, targetState),
            });
          }
        }
      }
    }
    return { goal, meta, steps: [] };
  }

  const GoalPlanner = { plan, parseGoal, defaultActions };
  if (typeof window !== 'undefined') window.GoalPlanner = GoalPlanner;
  if (typeof module !== 'undefined' && module.exports) module.exports = GoalPlanner;
})();
