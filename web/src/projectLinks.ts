import type { MaterialSelection } from './api';

export function isProjectLink(href: string) {
  return !/^(?:[a-z][a-z\d+.-]*:|[/\\])/i.test(href);
}

export function projectLink(source: string, href: string, workspace: string) {
  if (!isProjectLink(href)) throw new Error('请使用项目内的相对文件路径。');
  const root = new URL('https://project.invalid/');
  const base = new URL(source.split('/').map(encodeURIComponent).join('/'), root);
  const target = new URL(href, base);
  const path = decodeURIComponent(target.pathname.slice(1));
  if (target.origin !== root.origin || target.search || !path.startsWith(workspace + '/') ||
      path.includes('\\') || path.split('/').some(part => !part || part.startsWith('.'))) {
    throw new Error('链接指向无法查看的项目文件。');
  }

  let page: number | undefined;
  let selection: MaterialSelection | undefined;
  if (target.hash) {
    const fragment = decodeURIComponent(target.hash.slice(1));
    const location = /^(page|paragraph)=([1-9]\d*)$/.exec(fragment);
    if (!location || !Number.isSafeInteger(Number(location[2]))) {
      throw new Error('请使用 page 或 paragraph 指定页码或段号。');
    }
    const pdf = /\.pdf$/i.test(path);
    if ((location[1] === 'page') !== pdf) {
      throw new Error('PDF 链接使用页码，其他文档链接使用段号。');
    }
    const number = Number(location[2]);
    if (pdf) page = number;
    else selection = { startParagraph: number, endParagraph: number };
  }
  return { path, page, selection };
}
