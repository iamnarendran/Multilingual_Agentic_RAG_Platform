import { Workspace } from "@/components/workspace";

// The chat workspace lives in the layout so it stays mounted when the URL changes
// from "/" to "/c/<id>" (e.g. right after the first message creates a conversation).
export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Workspace />
      {children}
    </>
  );
}
