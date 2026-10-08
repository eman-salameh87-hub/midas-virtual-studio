import { useState } from "react";
import { runStudioStepTransition } from "../motion/studioMotion";
import { StudioShell } from "../components/layout/StudioShell";
import { ItemSection } from "../components/sections/ItemSection";
import { JobSection } from "../components/sections/JobSection";
import { ProjectItemSection } from "../components/sections/ProjectItemSection";
import { ProjectReviewSection } from "../components/sections/ProjectReviewSection";
import { ProjectScopeSection } from "../components/sections/ProjectScopeSection";
import { ProjectSection, type ProjectStart } from "../components/sections/ProjectSection";
import { PreferencesSection } from "../components/sections/PreferencesSection";
import { ReviewSection } from "../components/sections/ReviewSection";
import { ScopeSection } from "../components/sections/ScopeSection";
import { SuggestionsSection } from "../components/sections/SuggestionsSection";
import { primaryFlow, projectFlow } from "../flow";
import { referenceIssues, type ProjectPlace, type ProjectScopeOutput } from "../lib/projectBrief";
import { createEmptyBriefItem } from "../state/emptyDraft";
import { DraftProvider } from "../state/DraftProvider";
import type { ItemDraft, ReferencesDraft, SectionId } from "../types/draft";

type ProjectStep = (typeof projectFlow)[number]["id"] | "review";

export function ClientFirstPage() {
  return (
    <DraftProvider>
      <ClientFirstExperience />
    </DraftProvider>
  );
}

function ClientFirstExperience() {
  const [mode, setMode] = useState<"projects" | "manual">("manual");
  const [section, setSection] = useState<SectionId>("job");
  const [projectStep, setProjectStep] = useState<ProjectStep>("project");
  const [projectStart, setProjectStart] = useState<ProjectStart>("product_or_collection");
  const [existingRoom, setExistingRoom] = useState("");
  const [newStyledSpace, setNewStyledSpace] = useState("");
  const [projectItem, setProjectItem] = useState<ItemDraft>(() => createEmptyBriefItem().item);
  const [projectReferences, setProjectReferences] = useState<ReferencesDraft>(() => createEmptyBriefItem().references);
  const [projectOutputs, setProjectOutputs] = useState<ProjectScopeOutput[]>([]);
  const projectBrief = {
    start: projectStart,
    existingRoom,
    newStyledSpace,
    item: projectItem,
    references: projectReferences,
    outputs: projectOutputs,
  };
  function resetProject() {
    const empty = createEmptyBriefItem();
    setProjectStart("product_or_collection");
    setExistingRoom("");
    setNewStyledSpace("");
    setProjectItem(empty.item);
    setProjectReferences(empty.references);
    setProjectOutputs([]);
    setProjectStep("project");
  }

  function openSection(next: SectionId) {
    if (next === "references" || next === "advanced") {
      setSection("item");
      return;
    }
    setSection(next);
  }

  function openItemFromJob(update: () => void) {
    runStudioStepTransition(section === "job", update);
  }

  return (
    <StudioShell
      mode={mode}
      onMode={setMode}
      steps={mode === "projects" ? projectFlow : primaryFlow}
      section={mode === "projects" ? projectStep : section}
      onSection={(next) => {
        if (mode === "projects") {
          if (next === "project" || next === "item" || next === "scope") {
            runStudioStepTransition(projectStep === "project" && next === "item", () => setProjectStep(next));
          }
          return;
        }
        if (section === "job" && next === "item") {
          openItemFromJob(() => openSection("item"));
          return;
        }
        openSection(next as SectionId);
      }}
    >
      {mode === "projects" && projectStep === "project" ? (
        <ProjectSection
          start={projectStart}
          existingRoom={existingRoom}
          newStyledSpace={newStyledSpace}
          onStart={setProjectStart}
          onExistingRoom={setExistingRoom}
          onNewStyledSpace={setNewStyledSpace}
          onContinue={() => runStudioStepTransition(true, () => setProjectStep("item"))}
        />
      ) : null}
      {mode === "projects" && projectStep === "item" ? (
        <ProjectItemSection
          item={projectItem}
          references={projectReferences}
          onItem={setProjectItem}
          onReferences={setProjectReferences}
          onBack={() => setProjectStep("project")}
          onContinue={() => {
            if (referenceIssues(projectReferences).length > 0) return;
            setProjectStep("scope");
          }}
          issues={referenceIssues(projectReferences)}
        />
      ) : null}
      {mode === "projects" && projectStep === "scope" ? (
        <ProjectScopeSection
          outputs={projectOutputs}
          onOutputs={setProjectOutputs}
          onBack={() => setProjectStep("item")}
          onContinue={() => setProjectStep("review")}
        />
      ) : null}
      {mode === "projects" && projectStep === "review" ? (
        <ProjectReviewSection
          brief={projectBrief}
          onBack={() => setProjectStep("scope")}
          onEdit={(place: ProjectPlace) => setProjectStep(place)}
          onStartOver={resetProject}
        />
      ) : null}
      {mode === "manual" && section === "job" ? <JobSection onContinue={() => openItemFromJob(() => setSection("item"))} /> : null}
      {mode === "manual" && section === "item" ? (
        <ItemSection onBack={() => setSection("job")} onContinue={() => setSection("scope")} />
      ) : null}
      {mode === "manual" && section === "scope" ? (
        <ScopeSection onBack={() => setSection("item")} onContinue={() => setSection("preferences")} />
      ) : null}
      {mode === "manual" && section === "preferences" ? (
        <PreferencesSection onBack={() => setSection("scope")} onContinue={() => setSection("suggestions")} />
      ) : null}
      {mode === "manual" && section === "suggestions" ? (
        <SuggestionsSection onBack={() => setSection("preferences")} onContinue={() => setSection("review")} />
      ) : null}
      {mode === "manual" && section === "review" ? (
        <ReviewSection onBack={() => setSection("suggestions")} onNavigate={openSection} onStartOver={() => setSection("job")} />
      ) : null}
    </StudioShell>
  );
}
