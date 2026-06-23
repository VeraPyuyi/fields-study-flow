import { PaperLensApp } from "./PaperLensApp";
import { PaperMapApp } from "./PaperMapApp";
import { RoadmapApp } from "./RoadmapApp";
import { readPayload } from "./data";

export function App() {
  const payload = readPayload();
  if (payload.reportKind === "paper_map") {
    return <PaperMapApp roadmap={payload.roadmap} />;
  }
  if (payload.reportKind === "paper_lens") {
    return <PaperLensApp roadmap={payload.roadmap} />;
  }
  return <RoadmapApp roadmap={payload.roadmap} />;
}
