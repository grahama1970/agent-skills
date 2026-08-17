import { useCallback, useState } from "react";

import { useHUDHotkeys } from "@/hooks/useHUDHotkeys";

export function useDefinitionPeek() {
  const [isPeeking, setIsPeeking] = useState(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("peek") === "1";
  });

  const toggleDefinitionPeek = useCallback(() => {
    setIsPeeking((value) => !value);
  }, []);

  useHUDHotkeys([{ key: "Shift+P", handler: toggleDefinitionPeek }]);

  return { isPeeking, toggleDefinitionPeek };
}
