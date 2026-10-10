import { useId, useState } from "react";

export function AssetDropzone({
  title,
  hint,
  action,
  accept,
  onFiles,
}: {
  title: string;
  hint: string;
  action: string;
  accept: string;
  onFiles: (files: FileList) => void;
}) {
  const inputId = useId();
  const titleId = useId();
  const hintId = useId();
  const [dragging, setDragging] = useState(false);

  return (
    <label
      className="dropzone"
      data-active={dragging ? "true" : "false"}
      onDragEnter={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(event) => {
        if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
        setDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        if (event.dataTransfer.files.length > 0) onFiles(event.dataTransfer.files);
      }}
    >
      <input
        id={inputId}
        className="dropzone__input"
        type="file"
        accept={accept}
        multiple
        aria-labelledby={titleId}
        aria-describedby={hintId}
        onChange={(event) => {
          if (event.target.files && event.target.files.length > 0) onFiles(event.target.files);
          event.target.value = "";
        }}
      />
      <span id={titleId} className="dropzone__title">
        {dragging ? "Release to add" : title}
      </span>
      <span id={hintId} className="dropzone__hint">
        {hint}
      </span>
      <span className="dropzone__action">{action}</span>
    </label>
  );
}
