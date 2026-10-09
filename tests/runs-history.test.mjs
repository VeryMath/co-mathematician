import test from 'node:test';
import assert from 'node:assert/strict';
import { Runs } from '../server/runs.mjs';

const user = content => ({ role: 'user', content });
const assistant = (content, status = 'succeeded') => ({ role: 'assistant', content, status });
const plain = messages => messages.map(({ role, content }) => ({ role, content }));
const length = messages => messages.reduce((total, message) => total + message.content.length, 0);
const omission = /省略|节选|omitt?ed|truncat|excerpt/i;

function longMessage(size, label) {
  const start = `BEGIN_${label}: `;
  const end = ` :END_${label}`;
  return start + 'x'.repeat(size - start.length - end.length) + end;
}

async function requestHistory(messages, { skill = false } = {}) {
  let history;
  let begin;
  const core = {
    async call(method, params) {
      switch (method) {
        case 'project.read': return { workspace: '/example/workspace' };
        case 'file.read': return { content: '# Example project', readable: true };
        case 'skill.read': return { source: 'project', path: 'example/SKILL.md', name: 'example', title: 'Example', mode: 'skill_guided', resources: [], warnings: [] };
        case 'chat.read': return { messages };
        case 'chat.begin':
          begin = structuredClone(params);
          return { id: 'new-answer', role: 'assistant', content: '', status: 'running' };
        case 'chat.update': return params;
        default: throw new Error(`Unexpected Core method: ${method}`);
      }
    },
  };
  const model = {
    async selected() { return { model: { id: 'test-model' }, provider: 'test' }; },
    async generate(context) {
      history = structuredClone(context.history);
      context.onText('Test reply');
    },
  };
  const runs = new Runs(core, model);
  let finish;
  const finished = new Promise(resolve => { finish = resolve; });
  const unsubscribe = runs.subscribe('test-project', message => {
    if (message.status !== 'running') finish(message);
  });
  try {
    await runs.start('test-project', {
      content: 'Explain the previous proof.', files: [],
      ...(skill ? { skill: { source: 'project', path: 'example/SKILL.md' } } : {}),
    });
    const result = await finished;
    assert.equal(result.status, 'succeeded');
    return { history, begin };
  } finally {
    unsubscribe();
    await runs.close();
  }
}

function assertExcerpt(actual, original) {
  assert.ok(actual.startsWith(original.slice(0, 16)), 'excerpt preserves the message opening');
  assert.ok(actual.endsWith(original.slice(-16)), 'excerpt preserves the message conclusion');
  assert.match(actual, omission, 'excerpt explicitly marks omitted text');
  assert.ok(actual.length < original.length);
}

function assertHistoryNotice(begin) {
  assert.ok(begin.sourceNotes.some(note => /历史|history/i.test(note) && omission.test(note)), 'saved source notes disclose history excerpts');
}

test('preserves short conversations in chronological order without an excerpt notice', async () => {
  const messages = [user('First question'), assistant('First answer'), user('Follow-up'), assistant('Follow-up answer')];
  const { history, begin } = await requestHistory(messages);
  assert.deepEqual(history, plain(messages));
  assert.equal(begin.sourceNotes.some(note => /历史|history/i.test(note)), false);
});

for (const [skill, budget] of [[false, 12000], [true, 6000]]) {
  for (const answerLength of [budget, budget + 1]) {
    test(`${skill ? 'Skill' : 'normal'} history keeps the question and excerpts a ${answerLength}-character answer`, async () => {
      const question = 'Prove the claim step by step.';
      const answer = longMessage(answerLength, 'PROOF');
      const { history, begin } = await requestHistory([user(question), assistant(answer)], { skill });
      assert.deepEqual(history.map(message => message.role), ['user', 'assistant']);
      assert.equal(history[0].content, question);
      assertExcerpt(history[1].content, answer);
      assert.equal(length(history), budget, 'the excerpt marker is included in the character budget');
      assertHistoryNotice(begin);
    });
  }
}

test('preserves a short answer when the latest user message exceeds the budget', async () => {
  const question = longMessage(16000, 'QUESTION');
  const answer = 'Here is the short conclusion.';
  const { history, begin } = await requestHistory([user(question), assistant(answer)]);
  assert.deepEqual(history.map(message => message.role), ['user', 'assistant']);
  assertExcerpt(history[0].content, question);
  assert.equal(history[1].content, answer);
  assert.equal(length(history), 12000);
  assertHistoryNotice(begin);
});

test('shares the budget fairly when both messages in the latest turn are long', async () => {
  const question = longMessage(16000, 'QUESTION');
  const answer = longMessage(20000, 'ANSWER');
  const { history } = await requestHistory([user(question), assistant(answer)]);
  assert.deepEqual(history.map(message => message.role), ['user', 'assistant']);
  assertExcerpt(history[0].content, question);
  assertExcerpt(history[1].content, answer);
  assert.equal(history[0].content.length, 6000);
  assert.equal(history[1].content.length, 6000);
});

test('includes older complete turns that fit alongside the latest turn', async () => {
  const messages = [user('Earlier question'), assistant('Earlier answer'), user('Latest question'), assistant(longMessage(11000, 'ANSWER'))];
  const { history } = await requestHistory(messages);
  assert.deepEqual(history, plain(messages));
});

test('does not include a partial older turn when that turn exceeds the remaining budget', async () => {
  const oldQuestion = longMessage(6000, 'OLD_QUESTION');
  const messages = [user(oldQuestion), assistant('Old answer'), user('Latest question'), assistant(longMessage(7000, 'LATEST_ANSWER'))];
  const { history } = await requestHistory(messages);
  assert.deepEqual(history, plain(messages.slice(-2)));
});

test('gives the latest turn priority over older turns when it needs an excerpt', async () => {
  const messages = [user('Earlier question'), assistant('Earlier answer'), user('Latest question'), assistant(longMessage(13000, 'LATEST_ANSWER'))];
  const { history } = await requestHistory(messages);
  assert.deepEqual(history.map(message => message.role), ['user', 'assistant']);
  assert.equal(history[0].content, 'Latest question');
  assertExcerpt(history[1].content, messages[3].content);
  assert.equal(length(history), 12000);
});

test('considers at most the last twelve original messages', async () => {
  const messages = Array.from({ length: 8 }, (_, index) => [user(`Question ${index}`), assistant(`Answer ${index}`)]).flat();
  const { history } = await requestHistory(messages);
  assert.deepEqual(history, plain(messages.slice(-12)));
});

test('skips unsuccessful assistant replies without reaching beyond the twelve-message window', async () => {
  const messages = [user('Outside window'), assistant('Outside answer')];
  for (const status of ['failed', 'cancelled', 'interrupted', 'running']) {
    messages.push(user(`Question before ${status}`), assistant(`Reply ${status}`, status));
  }
  messages.push(user('Successful question'), assistant('Successful answer'), user('Latest question'), assistant('Latest answer'));
  const { history } = await requestHistory(messages);
  const expected = messages.slice(-12).filter(message => message.role !== 'assistant' || message.status === 'succeeded');
  assert.deepEqual(history, plain(expected));
});

test('does not mutate the stored history when producing excerpts', async () => {
  const messages = [user('Question'), { ...assistant(longMessage(15000, 'ANSWER')), id: 'saved-answer', sourceNotes: ['Saved source'] }];
  const original = structuredClone(messages);
  Object.freeze(messages);
  for (const message of messages) Object.freeze(message);
  await requestHistory(messages);
  assert.deepEqual(messages, original);
});

test('does not split Unicode surrogate pairs at either excerpt boundary', async () => {
  for (const question of ['Q', 'QQ', 'QQQ', 'QQQQ']) {
    const answer = '😀'.repeat(7000);
    const { history } = await requestHistory([user(question), assistant(answer)]);
    assert.deepEqual(history.map(message => message.role), ['user', 'assistant']);
    assert.equal(history[0].content, question);
    assertExcerpt(history[1].content, answer);
    assert.equal(history[1].content.isWellFormed(), true, 'head and tail contain no unpaired surrogate');
    assert.ok(length(history) <= 12000);
    assert.ok(length(history) >= 11998, 'only boundary surrogate adjustments reduce the available budget');
  }
});
