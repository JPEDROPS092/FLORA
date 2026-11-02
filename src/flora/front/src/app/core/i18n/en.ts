import { EN_AGENTS } from './en/agents';
import { EN_APP } from './en/app';
import { EN_DATA } from './en/data';
import { EN_PAGES } from './en/pages';
import { EN_WELCOME } from './en/welcome';

/** English dictionary, keyed by the Portuguese source string. One file per area. */
export const EN: Record<string, string> = { ...EN_APP, ...EN_AGENTS, ...EN_DATA, ...EN_PAGES, ...EN_WELCOME };
