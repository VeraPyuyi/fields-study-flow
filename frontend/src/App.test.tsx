import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { vi } from "vitest";
import { App } from "./App";
import stylesCss from "./styles.css?raw";

function installPayload(payload: unknown) {
  document.body.innerHTML = '<div id="root"></div><script type="application/json" id="fields-study-flow-data"></script>';
  const script = document.getElementById("fields-study-flow-data");
  if (script) script.textContent = JSON.stringify(payload);
}

afterEach(() => {
  document.body.innerHTML = "";
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("fields-study-flow React report app", () => {
  it("does not clip Paper Map node text with fixed-height hidden overflow", () => {
    expect(stylesCss).not.toMatch(/\.map-node\s*\{[^}]*\bmax-height\s*:/s);
    expect(stylesCss).not.toMatch(/\.map-node\s*\{[^}]*\boverflow\s*:\s*hidden\b/s);
    expect(stylesCss).not.toMatch(/\.map-node strong\s*\{[^}]*\bmax-height\s*:/s);
    expect(stylesCss).not.toMatch(/\.map-node strong\s*\{[^}]*\boverflow\s*:\s*hidden\b/s);
    expect(stylesCss).not.toMatch(/\.map-node p\s*\{[^}]*\bmax-height\s*:/s);
    expect(stylesCss).not.toMatch(/\.map-node p\s*\{[^}]*\boverflow\s*:\s*hidden\b/s);
  });

  it("keeps long report text intact instead of inserting visible ellipses", () => {
    const longPaperTitle =
      "Teaching LLMs to Plan Logical Chain-of-Thought Instruction Tuning for Symbolic Planning with Detailed Evidence Coverage";
    const longNodeText =
      "This node explains how background motivation problem methodology experiments contributions and limitations connect into one readable paper map";
    installPayload({
      reportKind: "paper_map",
      roadmap: {
        title: longPaperTitle,
        profile: { goal: longPaperTitle, output_language: "zh-CN" },
        paper_map: {
          target: { title: longPaperTitle },
          nodes: [
            {
              id: "target",
              role: "target",
              kind: "target",
              label: longPaperTitle,
              plain_explanation: longNodeText,
              evidence: [{ resource_title: "Target PDF", snippet: "Evidence coverage" }],
            },
          ],
          edges: [],
        },
      },
    });

    render(<App />);

    expect(document.body.textContent).toContain("Detailed Evidence Coverage");
    expect(document.body.textContent).toContain("readable paper map");
    expect(document.body.textContent).not.toContain("...");
    expect(document.body.textContent).not.toContain("…");
  });

  it("renders the roadmap learning console from embedded JSON", () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    const createObjectURL = vi.fn(() => "blob:mastery-worksheet");
    const revokeObjectURL = vi.fn();
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: createObjectURL,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: revokeObjectURL,
    });

    installPayload({
      reportKind: "roadmap",
      roadmap: {
        title: "Transformer 学习路线",
        profile: { goal: "掌握 Transformer", output_language: "zh-CN" },
        path_strategy: { estimated_total_time: "3h", mode: "fastest" },
        paper_map: { nodes: [{ id: "target", label: "Transformer" }], edges: [] },
        paper_lens: { segments: [{ id: "seg-1", original_text: "Attention is all you need." }] },
        phases: [{ name: "阶段 1", objective: "理解注意力机制", estimated_time: "1h" }],
        study_tasks: [
          {
            id: "task-explain",
            type: "explain",
            title: "解释核心问题",
            evidence: "不看笔记讲清论文问题。",
            acceptance: "别人能听懂问题和贡献。",
            estimated_minutes: 20,
            resource_titles: ["Local PDF"],
          },
          {
            id: "task-derive",
            type: "derive",
            title: "推导关键机制",
            evidence: "用自己的话拆解公式或机制。",
            acceptance: "能说明每一步为什么成立。",
            estimated_minutes: 30,
            evidence_chunks: [{}],
          },
          {
            id: "task-reproduce",
            type: "reproduce",
            title: "复现最小实验",
            evidence: "留下命令输出或 notebook 结果。",
            acceptance: "有可复查结果。",
            estimated_minutes: 60,
            resource_titles: ["Copied Notebook"],
          },
        ],
        study_bundle: {
          readme_file: "README.md",
          readme_href: "../study-assets/README.md",
          links_file: "links.md",
          links_href: "../study-assets/links.md",
          retry_href: "../study-assets/retry_failed.md",
          download_queue_href: "../study-assets/download_queue.json",
          download_manager: { retry_file: "retry_failed.md", download_queue_file: "download_queue.json" },
          summary: { total: 4, completed: 2, downloaded: 1, copied: 1, failed: 1, "link-only": 1 },
          resources: [
            {
              title: "Local PDF",
              local_href: "../assets/a.pdf",
              type: "paper",
              status: "downloaded",
              metadata: { rag: { evidence_chunks: [{ snippet: "Explains the main claim.", file_name: "a.pdf" }] } },
            },
            {
              title: "Copied Notebook",
              local_href: "../assets/b.ipynb",
              type: "notebook",
              status: "copied",
              metadata: { rag: { evidence_chunks: [{ snippet: "Shows a minimal reproduction.", file_name: "b.ipynb" }] } },
            },
            { title: "Broken Repo", url: "https://example.com/repo", type: "repository", status: "failed" },
            { title: "Manual Link", url: "https://example.com/book", type: "book", status: "link-only" },
          ],
        },
      },
    });

    render(<App />);
    const resourceLibrary = document.querySelector("#resource-library") as HTMLElement;
    const readinessPanel = document.querySelector("[data-roadmap-mastery-readiness]") as HTMLElement;
    const readinessGates = Array.from(document.querySelectorAll("[data-roadmap-mastery-gate]"));

    expect(screen.getByText("学习中控台")).toBeInTheDocument();
    expect(readinessPanel).toBeInTheDocument();
    expect(within(readinessPanel).getByText("63%")).toBeInTheDocument();
    expect(readinessGates).toHaveLength(4);
    expect(document.querySelector('[data-roadmap-mastery-gate="explain"]')).toHaveAttribute("data-roadmap-mastery-status", "ready");
    expect(document.querySelector('[data-roadmap-mastery-gate="reproduce"]')).toHaveAttribute("data-roadmap-mastery-status", "ready");
    expect(document.querySelector('[data-roadmap-mastery-gate="derive"]')).toHaveAttribute("data-roadmap-mastery-status", "needs_evidence");
    expect(document.querySelector('[data-roadmap-mastery-gate="critique"]')).toHaveAttribute("data-roadmap-mastery-status", "missing");
    expect(screen.getByText("先从这里开始")).toBeInTheDocument();
    expect(screen.getByText("1 先看论文逻辑图")).toBeInTheDocument();
    expect(screen.getByText("2 再做段落精读")).toBeInTheDocument();
    expect(screen.getByText("3 最后按任务验收")).toBeInTheDocument();
    expect(screen.getByText("1分钟上手")).toBeInTheDocument();
    expect(screen.getByText("先点论文逻辑图")).toBeInTheDocument();
    expect(screen.getByText("打开一份本地资料")).toBeInTheDocument();
    expect(screen.getByText("勾掉第一个验收任务")).toBeInTheDocument();
    expect(screen.getByText("资料包完成率")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("打开资料包说明")).toBeInTheDocument();
    expect(screen.getByText("原始链接清单")).toBeInTheDocument();
    expect(screen.getByText("重试失败项")).toBeInTheDocument();
    expect(screen.getByText("下载队列")).toBeInTheDocument();
    expect(screen.getByText("把学习变成可检查证据")).toBeInTheDocument();
    expect(screen.getByText("0/3 · 0%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制证据清单" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "下载 worksheet.md" })).toBeInTheDocument();
    expect(screen.getByLabelText("解释")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("解释"));
    expect(screen.getByText("1/3 · 33%")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "复制证据清单" }));
    const copiedWorksheet = String(writeText.mock.calls[0]?.[0] || "");
    expect(copiedWorksheet).toContain("Ready-to-present rule");
    expect(copiedWorksheet).toContain("Source anchors to use");
    expect(copiedWorksheet).toContain("Ready-to-present checkpoint");
    expect(copiedWorksheet).toContain("Explains the main claim.");
    expect(copiedWorksheet).toContain("Shows a minimal reproduction.");
    expect(copiedWorksheet).toContain("Copied Notebook");
    expect(copiedWorksheet).not.toContain("D:\\");
    fireEvent.click(screen.getByRole("button", { name: "下载 worksheet.md" }));
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(anchorClick).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mastery-worksheet");
    expect(screen.getAllByText("本地可打开").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("下载失败").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("仅链接").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("阶段 1")).toBeInTheDocument();
    expect(screen.getAllByText("打开本地").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByLabelText("搜索资料")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "全部资料" })).toBeInTheDocument();
    expect(within(resourceLibrary).getByText("Local PDF")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "下载失败" }));
    expect(within(resourceLibrary).getByText("Broken Repo")).toBeInTheDocument();
    expect(within(resourceLibrary).queryByText("Local PDF")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "全部资料" }));
    fireEvent.change(screen.getByLabelText("搜索资料"), { target: { value: "notebook" } });
    expect(within(resourceLibrary).getByText("Copied Notebook")).toBeInTheDocument();
    expect(within(resourceLibrary).queryByText("Manual Link")).not.toBeInTheDocument();
  });

  it("shows recovery next steps when a roadmap has no phases tasks or resources", () => {
    installPayload({
      reportKind: "roadmap",
      roadmap: {
        title: "Sparse route",
        profile: { goal: "Learn sparse topic", output_language: "zh-CN" },
        phases: [],
        study_tasks: [],
        study_bundle: { summary: { total: 0 }, resources: [] },
      },
    });

    render(<App />);
    const readinessPanel = document.querySelector("[data-roadmap-mastery-readiness]") as HTMLElement;

    expect(screen.getByText("下一步补齐路线")).toBeInTheDocument();
    expect(readinessPanel).toBeInTheDocument();
    expect(within(readinessPanel).getByText("0%")).toBeInTheDocument();
    expect(document.querySelectorAll('[data-roadmap-mastery-status="missing"]')).toHaveLength(4);
    expect(screen.getByText("补齐学习阶段")).toBeInTheDocument();
    expect(screen.getByText(/补充目标论文或本地资料/)).toBeInTheDocument();
    expect(screen.getByText("补齐验收任务")).toBeInTheDocument();
    expect(screen.getByText(/至少生成解释、推导、复现、批判/)).toBeInTheDocument();
    expect(screen.getByText("暂无学习阶段")).toBeInTheDocument();
    expect(screen.getByText("暂无验收任务")).toBeInTheDocument();
    expect(screen.getByText("暂无可打开资料")).toBeInTheDocument();
  });

  it("renders Paper Lens as paragraph-level reading instead of sentence cards", () => {
    installPayload({
      reportKind: "paper_lens",
      roadmap: {
        title: "Planning Paper",
        profile: { output_language: "zh-CN" },
        paper_lens: {
          target: { title: "Planning Paper" },
          explanation_summary: { granularity: "paragraph" },
          sections: [{ kind: "method", title: "方法" }],
          segments: [
            {
              id: "seg-1",
              section_kind: "method",
              section_title: "方法",
              unit: "paragraph",
              paragraph_index: 1,
              sentence_count: 3,
              original_text: "This paragraph explains how logical traces check preconditions, apply effects, and update states.",
            },
          ],
          inline_explanations: [
            {
              segment_id: "seg-1",
              plain_meaning: "这段把方法讲成一个可检查的状态更新过程。",
              why_it_matters: "它解释了为什么规划不是随便生成文本。",
              method_note: "先看前提，再应用效果，最后检查新状态。",
              confidence: 0.78,
            },
          ],
        },
      },
    });

    render(<App />);

    expect(screen.getByText("段落式论文精读")).toBeInTheDocument();
    expect(screen.getByText("段落解释支撑度")).toBeInTheDocument();
    expect(screen.getByText("中（0.78）")).toBeInTheDocument();
    expect(screen.getByText(/不是资源可信度/)).toBeInTheDocument();
    expect(screen.queryByText("证据置信度")).not.toBeInTheDocument();
    expect(screen.getByText(/不是绝对正确率/)).toBeInTheDocument();
    expect(screen.getAllByText("这段把方法讲成一个可检查的状态更新过程。")).toHaveLength(1);
    expect(screen.getByText("右侧正在显示这段的直白解释、方法理解和证据。")).toBeInTheDocument();
    expect(screen.queryByText("关键句速读")).not.toBeInTheDocument();
  });

  it("shows purpose badges that explain why roadmap resources matter", () => {
    installPayload({
      reportKind: "roadmap",
      roadmap: {
        title: "Resource badge route",
        profile: { goal: "Understand one paper", output_language: "zh-CN" },
        study_bundle: {
          resources: [
            {
              title: "Target Paper PDF",
              local_href: "assets/paper.pdf",
              source: "arxiv",
              type: "paper",
              status: "downloaded",
              trust_score: 0.96,
              score: 0.91,
              concepts: ["PDDL action preconditions"],
              focus_areas: ["methodology", "experiment"],
              metadata: { target_paper: true },
              why_recommended: "Target paper for claims and experiments.",
            },
            {
              title: "Reference Implementation",
              local_href: "assets/code.zip",
              source: "github",
              type: "repository",
              status: "copied",
              trust_score: 0.81,
              score: 0.78,
              why_recommended: "Implementation support for reproduction.",
            },
            { title: "Planning Background", url: "https://example.com/book", type: "book", status: "link-only" },
            { title: "Weak Related Paper", url: "https://example.com/weak-paper", type: "paper", status: "link-only" },
            { title: "Validation Checklist", local_href: "artifact_template/task_checklist.md", type: "template", status: "generated" },
          ],
        },
        paper_map: {
          nodes: [
            { id: "background", kind: "background", label: "Planning background" },
            { id: "methodology", kind: "methodology", label: "Logical CoT methodology" },
            { id: "experiment", kind: "experiment", label: "PlanBench experiment" },
          ],
          edges: [],
        },
        resource_library: [
          {
            title: "Target Paper PDF",
            metadata: {
              rag: {
                evidence_score: 2.5,
                evidence_chunks: [
                  {
                    snippet: "PDDL preconditions and VAL validation directly support the planning evidence.",
                    score: 2.5,
                    detail_anchor: "detail-seg-pddl-validation",
                  },
                ],
              },
            },
          },
        ],
      },
    });

    render(<App />);
    const resourceLibrary = document.querySelector("#resource-library") as HTMLElement;

    expect(within(resourceLibrary).getByText("主证据")).toBeInTheDocument();
    expect(within(resourceLibrary).getByText("代码/复现")).toBeInTheDocument();
    expect(within(resourceLibrary).getByText("背景补充")).toBeInTheDocument();
    expect(within(resourceLibrary).getByText("验收材料")).toBeInTheDocument();
    expect(within(resourceLibrary).getByText("核心资料")).toBeInTheDocument();
    expect(within(resourceLibrary).getByText("推荐补充")).toBeInTheDocument();
    expect(within(resourceLibrary).getAllByText("手动兜底").length).toBeGreaterThanOrEqual(1);
    expect(within(resourceLibrary).getByText(/证据强度：高/)).toBeInTheDocument();
    expect(within(resourceLibrary).getAllByText(/依据：本地可打开/).length).toBeGreaterThanOrEqual(1);
    expect(within(resourceLibrary).getByText(/证据分 2.50/)).toBeInTheDocument();
    expect(within(resourceLibrary).getByText(/可信分 0.96/)).toBeInTheDocument();
    expect(within(resourceLibrary).getByText(/最强证据：PDDL preconditions and VAL validation/)).toBeInTheDocument();
    expect(within(resourceLibrary).getByRole("link", { name: "查看证据" })).toHaveAttribute(
      "href",
      "paper_lens.html#detail-seg-pddl-validation",
    );
    expect(within(resourceLibrary).getByText(/推荐理由：Target paper for claims and experiments/)).toBeInTheDocument();
    expect(within(resourceLibrary).getByText(/为什么读：定位论文原始论点/)).toBeInTheDocument();
    expect(within(resourceLibrary).getByText(/为什么读：把理解变成可运行或可检查的结果/)).toBeInTheDocument();

    expect(within(resourceLibrary).getByText("目标论文")).toBeInTheDocument();
    expect(within(resourceLibrary).getByText("代码来源")).toBeInTheDocument();
    expect(within(resourceLibrary).getByText("生成模板")).toBeInTheDocument();
    expect(within(resourceLibrary).getByText("Weak Related Paper")).toBeInTheDocument();
    expect(within(resourceLibrary).getByText("尚未匹配到明确论文环节，适合作为补充阅读或手动核验资料。")).toBeInTheDocument();
    expect(within(resourceLibrary).getAllByText("覆盖范围").length).toBeGreaterThanOrEqual(1);
    expect(within(resourceLibrary).getAllByText("方法").length).toBeGreaterThanOrEqual(1);
    expect(within(resourceLibrary).getAllByText("实验").length).toBeGreaterThanOrEqual(1);
    expect(within(resourceLibrary).getAllByText(/覆盖 3 个学习面/).length).toBeGreaterThanOrEqual(1);

    fireEvent.change(screen.getByLabelText("搜索资料"), { target: { value: "VAL validation" } });
    expect(within(resourceLibrary).getByText("Target Paper PDF")).toBeInTheDocument();
    expect(within(resourceLibrary).queryByText("Reference Implementation")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("搜索资料"), { target: { value: "目标论文" } });
    expect(within(resourceLibrary).getByText("Target Paper PDF")).toBeInTheDocument();
    expect(within(resourceLibrary).queryByText("Reference Implementation")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("搜索资料"), { target: { value: "复现" } });
    expect(within(resourceLibrary).getByText("Reference Implementation")).toBeInTheDocument();
  });

  it("renders a paper set synthesis panel when multiple papers are present", () => {
    installPayload({
      reportKind: "roadmap",
      roadmap: {
        title: "Diffusion paper set",
        profile: { goal: "compare diffusion papers", output_language: "en" },
        paper_set: {
          mode: "paper-set",
          summary: { paper_count: 3, selected_paper_count: 2, shared_concept_count: 1 },
          papers: [
            { id: "paper-1", title: "Denoising Diffusion Probabilistic Models", selected: true, role: "anchor" },
            { id: "paper-2", title: "Score-Based Generative Modeling through SDEs", selected: true, role: "bridge" },
            { id: "paper-3", title: "Classifier-Free Diffusion Guidance", selected: false, role: "comparison" },
          ],
          shared_concepts: [{ label: "diffusion models", paper_count: 3, paper_ids: ["paper-1", "paper-2", "paper-3"] }],
          reading_order: [
            { position: 1, paper_id: "paper-1", title: "Denoising Diffusion Probabilistic Models", reason: "Start here." },
            { position: 2, paper_id: "paper-2", title: "Score-Based Generative Modeling through SDEs", reason: "Read next." },
          ],
          comparison_axes: [
            { id: "method", label: "Method", prompt: "Compare mechanism." },
            { id: "evaluation", label: "Evaluation evidence", prompt: "Compare evidence." },
          ],
          synthesis_tasks: [
            { type: "compare", title: "Compare how each paper frames diffusion models.", evidence: ["paper-1", "paper-2"] },
            { type: "synthesize", title: "Write one synthesis paragraph.", evidence: ["paper-1", "paper-2"] },
          ],
        },
      },
    });

    render(<App />);

    expect(screen.getByText(/Paper set synthesis/)).toBeInTheDocument();
    expect(screen.getByText("Denoising Diffusion Probabilistic Models")).toBeInTheDocument();
    expect(screen.getByText("diffusion models")).toBeInTheDocument();
    expect(screen.getByText("Evaluation evidence")).toBeInTheDocument();
    expect(screen.getByText("Write one synthesis paragraph.")).toBeInTheDocument();
  });

  it("keeps Paper Map focused on the core chain until supporting branches are requested", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    const createObjectURL = vi.fn(() => "blob:presentation-script");
    const revokeObjectURL = vi.fn();
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: createObjectURL,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: revokeObjectURL,
    });

    installPayload({
      reportKind: "paper_map",
      roadmap: {
        title: "Teaching LLMs to Plan",
        profile: { output_language: "zh-CN" },
        paper_map: {
          target: { title: "Teaching LLMs to Plan" },
          nodes: [
            {
              id: "target",
              role: "target",
              kind: "target",
              label: "Teaching LLMs to Plan",
              plain_explanation: "目标论文",
              evidence: [{ resource_title: "Target PDF", snippet: "Logical Chain-of-Thought Instruction Tuning" }],
            },
            {
              id: "background",
              role: "core",
              kind: "background",
              label: "符号规划背景",
              plain_explanation: "先理解规划为什么需要规则约束。",
              talking_point: "先交代符号规划要求每一步动作都合法。",
              evidence: [{ resource_title: "Target PDF", snippet: "symbolic planning requires valid action sequences" }],
            },
            { id: "methodology", role: "core", kind: "methodology", label: "Logical CoT 方法", plain_explanation: "用逻辑轨迹解释每一步动作。", talking_point: "再说明 Logical CoT 如何把动作选择变成可检查轨迹。" },
            { id: "resource-pddl", role: "resource", kind: "resource", label: "PDDL Notes", plain_explanation: "补充资料" },
            { id: "task-report", role: "task", kind: "task", label: "汇报任务", plain_explanation: "验收任务" },
          ],
          edges: [
            { from: "target", to: "background", label: "supports" },
            { from: "background", to: "methodology", label: "motivates" },
            { from: "methodology", to: "resource-pddl", label: "supports" },
            { from: "methodology", to: "task-report", label: "required_for" },
          ],
        },
      },
    });

    render(<App />);

    expect(screen.getByText("先看主链")).toBeInTheDocument();
    expect(screen.getByText("再点节点")).toBeInTheDocument();
    expect(screen.getByText("最后展开资料")).toBeInTheDocument();
    expect(screen.getByText("3 分钟汇报稿")).toBeInTheDocument();
    expect(screen.getByText("按这条线讲：背景 → 动机 → 问题 → 方法 → 实验 → 贡献 → 局限")).toBeInTheDocument();
    expect(screen.getByText("先交代符号规划要求每一步动作都合法。")).toBeInTheDocument();
    expect(screen.getByText("再说明 Logical CoT 如何把动作选择变成可检查轨迹。")).toBeInTheDocument();
    expect(screen.getAllByText("证据覆盖：已绑定 1 条").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("原文证据已绑定，可直接点节点复核。")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "复制汇报稿" }));
    expect(await screen.findByText("已复制，可直接粘贴到 PPT 备注或文档。")).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining("《Teaching LLMs to Plan》3 分钟汇报稿"));
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining("先交代符号规划要求每一步动作都合法。"));
    fireEvent.click(screen.getByRole("button", { name: "下载汇报稿.md" }));
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(anchorClick).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:presentation-script");
    expect(screen.getByText("阅读密度")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /速览主链/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /完整探索/ })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText("默认只显示目标论文和核心因果链，先让用户在 3 分钟内看懂论文为什么这样做。")).toBeInTheDocument();
    expect(screen.getByText("符号规划背景")).toBeInTheDocument();
    expect(screen.queryByText("PDDL Notes")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /完整探索/ }));

    expect(screen.getByText("PDDL Notes")).toBeInTheDocument();
    expect(screen.getByText("汇报任务")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /完整探索/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("显示资料、证据、公式和验收任务，用来做复查、实现和汇报准备。")).toBeInTheDocument();
  });

  it("deduplicates repeated target titles in Paper Lens headers", () => {
    const paperTitle = "Teaching LLMs to Plan: Logical Chain-of-Thought Instruction Tuning for Symbolic Planning";
    installPayload({
      reportKind: "paper_lens",
      roadmap: {
        title: `学习路线: 快速理解并能够中文汇报 ${paperTitle}: ${paperTitle}`,
        profile: { goal: `快速理解并能够中文汇报 ${paperTitle}: ${paperTitle}`, output_language: "zh-CN" },
        paper_lens: {
          title: "Teaching LLMs to Plan 目标论文增强阅读器",
          target_papers: [{ title: paperTitle, url: "local://private-paper" }],
          explanation_summary: { granularity: "paragraph" },
          sections: [{ kind: "abstract", title: "一遍读懂论文" }],
          segments: [
            {
              id: "seg-1",
              section_kind: "abstract",
              section_title: "一遍读懂论文",
              unit: "paragraph",
              original_text: "This paragraph states the paper problem and contribution.",
            },
          ],
          inline_explanations: [{ segment_id: "seg-1", plain_meaning: "这段说明论文要解决什么问题。" }],
        },
      },
    });

    render(<App />);

    expect(screen.getByRole("heading", { name: "Teaching LLMs to Plan 目标论文增强阅读器" })).toBeInTheDocument();
    expect(screen.getByText("快速理解并能够中文汇报")).toBeInTheDocument();
    expect(screen.queryByText(`快速理解并能够中文汇报 ${paperTitle}: ${paperTitle}`)).not.toBeInTheDocument();
    expect(document.querySelector('a[href^="local://"]')).toBeNull();
  });
});
