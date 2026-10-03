function historyExcerpt(content, allowance) {
  if (content.length <= allowance) return content;
  const marker = '\n\n[历史消息节选：中间内容已省略]\n\n';
  const available = allowance - marker.length;
  let headEnd = Math.ceil(available / 2);
  let tailStart = content.length - Math.floor(available / 2);
  // Keep Unicode characters intact at both excerpt boundaries.
  if (/[\uD800-\uDBFF]/.test(content[headEnd - 1])) headEnd--;
  if (/[\uDC00-\uDFFF]/.test(content[tailStart])) tailStart++;
  return content.slice(0, headEnd) + marker + content.slice(tailStart);
}

export class Runs {
  constructor(core, model) {
    this.core = core; this.model = model;
    this.active = new Map(); this.listeners = new Map();
  }

  publish(projectId, message) {
    for (const listener of this.listeners.get(projectId) || []) listener(message);
  }

  subscribe(projectId, listener) {
    if (!this.listeners.has(projectId)) this.listeners.set(projectId, new Set());
    this.listeners.get(projectId).add(listener);
    return () => {
      this.listeners.get(projectId)?.delete(listener);
      if (!this.listeners.get(projectId)?.size) this.listeners.delete(projectId);
    };
  }

  async start(projectId, input) {
    if (this.active.has(projectId)) throw Object.assign(new Error('这个项目正在生成回答，请等待或停止当前回答。'), { status: 409 });
    if (this.active.size >= 3) throw Object.assign(new Error('同时最多运行三个项目，请等待现有回答结束。'), { status: 409 });
    if (typeof input.content !== 'string' || !input.content.trim() || input.content.length > 20000 || !Array.isArray(input.files) || input.files.length > 6 || input.files.some(f => typeof f !== 'string')) {
      throw Object.assign(new Error('问题不能为空，可附带最多六份材料。'), { status: 400 });
    }
    const controller = new AbortController();
    const entry = { controller, message: null, completion: null };
    this.active.set(projectId, entry);
    try {
      const selection = await this.model.selected(input);
      let skill = null;
      if (input.skill) {
        if (!['project', 'verymath'].includes(input.skill.source) || typeof input.skill.path !== 'string') throw Object.assign(new Error('请选择可用的 Skill。'), { status: 400 });
        if (input.skill.source === 'verymath' && typeof input.skill.directory !== 'string') throw Object.assign(new Error('请重新选择 VeryMath Skill。'), { status: 400 });
        skill = await this.core.call('skill.read', { projectId, source: input.skill.source, path: input.skill.path, directory: input.skill.directory });
      }
      const project = await this.core.call('project.read', { projectId });
      const main = `${project.workspace.split(/[\\/]/).at(-1)}/project/PROJECT.md`;
      const sources = [...new Set([main, ...input.files])];
      const documents = [];
      const sourceNotes = [];
      let materialBudget = skill ? 14000 : 22000;
      for (const [index, path] of sources.entries()) {
        const document = await this.core.call('file.read', { projectId, path });
        if (document.readable === false) throw Object.assign(new Error(`${path} 暂时没有可供模型阅读的文字，请先移除该材料或转换为文本。`), { status: 400 });
        const allowance = Math.floor(materialBudget / (sources.length - index));
        const excerpt = document.content.slice(0, allowance);
        const shortened = document.content.length > allowance || document.truncated;
        if (shortened) sourceNotes.push(`${path}：本次仅使用开头节选。`);
        if (document.note) sourceNotes.push(`${path}：${document.note}`);
        documents.push({ path, content: excerpt, ...(shortened ? { note: '这是文件开头的节选，不代表完整材料。' } : {}) });
        materialBudget -= excerpt.length;
      }
      const conversation = await this.core.call('chat.read', { projectId });
      const turns = [];
      for (const message of conversation.messages.slice(-12)) {
        if (message.role === 'assistant' && message.status !== 'succeeded') continue;
        if (message.role === 'user' || !turns.length) turns.push([]);
        turns.at(-1).push({ role: message.role, content: message.content });
      }
      const history = [];
      let remaining = skill ? 6000 : 12000;
      for (const turn of turns.reverse()) {
        const length = turn.reduce((total, message) => total + message.content.length, 0);
        if (length > remaining) {
          if (history.length) break;
          // Preserve the latest question and answer together. Short messages keep
          // their full text; longer ones share the remaining character budget.
          const allowances = new Map();
          [...turn].sort((a, b) => a.content.length - b.content.length).forEach((message, index) => {
            const allowance = Math.min(message.content.length, Math.floor(remaining / (turn.length - index)));
            allowances.set(message, allowance);
            remaining -= allowance;
          });
          history.push(...turn.map(message => ({ ...message, content: historyExcerpt(message.content, allowances.get(message)) })));
          sourceNotes.push('历史对话：最近一轮较长，本次仅使用开头和结尾节选；完整记录仍保存在项目中。');
          break;
        }
        history.unshift(...turn);
        remaining -= length;
      }
      controller.signal.throwIfAborted();
      const skillInfo = skill ? { source: skill.source, path: skill.path, name: skill.name, title: skill.title, mode: skill.mode, resources: skill.resources.map(resource => resource.path), warnings: skill.warnings } : undefined;
      entry.message = await this.core.call('chat.begin', { projectId, content: input.content, sources, sourceNotes, model: selection.model.id, profileName: selection.profileName, provider: selection.provider, skill: skillInfo });
      entry.completion = this.execute(projectId, entry, { selection, question: input.content, documents, history, skill });
      return entry.message;
    } catch (error) { this.active.delete(projectId); throw error; }
  }

  async execute(projectId, entry, context) {
    let saving = Promise.resolve();
    const persist = () => {
      const state = { projectId, runId: entry.message.id, ...entry.message };
      saving = saving.then(() => this.core.call('chat.update', state));
      return saving;
    };
    let dirty = false;
    let persistenceError = null;
    const interval = setInterval(() => {
      if (!dirty || persistenceError) return;
      dirty = false;
      persist().catch(error => { persistenceError = error; entry.controller.abort(); });
    }, 1000);
    const timeout = setTimeout(() => entry.controller.abort(new Error('本次回答超过十分钟，已停止。')), 600_000);
    try {
      await this.model.generate({ ...context, signal: entry.controller.signal, onText: delta => {
        entry.message.content += delta;
        if (entry.message.content.length > 100000) entry.controller.abort(new Error('回答过长，已停止。'));
        dirty = true; this.publish(projectId, entry.message);
      } });
      if (!entry.message.content.trim()) throw new Error('模型没有返回文字，请检查模型设置。');
      entry.message.status = 'succeeded';
    } catch (error) {
      entry.message.status = entry.controller.signal.aborted && !persistenceError ? 'cancelled' : 'failed';
      entry.message.error = persistenceError ? '保存回答失败，请复制当前文字后检查项目目录。' : entry.controller.signal.aborted ? entry.controller.signal.reason?.message || '已停止生成，已有文字保留。' : error.message;
    } finally {
      clearInterval(interval); clearTimeout(timeout);
      try { await saving; await persist(); }
      catch { entry.message.status = 'failed'; entry.message.error = '保存回答失败，请复制当前文字。'; }
      this.publish(projectId, entry.message);
      this.active.delete(projectId);
    }
  }

  cancel(projectId) {
    const entry = this.active.get(projectId);
    if (entry) entry.controller.abort(new Error('已停止生成，已有文字保留。'));
    return { stopped: !!entry };
  }

  async close() {
    for (const entry of this.active.values()) entry.controller.abort(new Error('应用已关闭，已有文字保留。'));
    await Promise.allSettled([...this.active.values()].map(entry => entry.completion));
  }
}
