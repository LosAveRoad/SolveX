import type { Role } from "../events/types.js";

/** 按角色收紧的工具白名单；review 为只读，从根上消除 A2/F3（评审覆写 master_plan）。 */
export const ROLE_TOOLS: Record<Role, string[]> = {
  modeling: ["read", "grep", "find", "ls", "bash", "python_execute",
             "arxiv_search", "web_search", "webReader", "write", "edit"],
  programming: ["read", "write", "edit", "bash", "python_execute"],
  review: ["read", "grep", "find", "ls"],
  writing: ["read", "write", "edit"],
  visualization: ["read", "write", "edit", "bash", "python_execute"],
};

export const REVIEW_TOOLS = ROLE_TOOLS.review;
