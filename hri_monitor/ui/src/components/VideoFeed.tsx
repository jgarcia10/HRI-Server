export function VideoFeed({ title, src }: { title: string; src: string }) {
  return (
    <div className="rounded-xl bg-slate-900 border border-slate-800 p-4">
      <h3 className="text-sm font-medium text-slate-400 mb-2">{title}</h3>
      <img src={src} alt={title}
           className="w-full rounded-lg bg-black aspect-video object-contain" />
    </div>
  );
}
