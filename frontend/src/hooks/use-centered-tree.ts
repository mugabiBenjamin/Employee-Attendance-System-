import { useState, useCallback, type RefObject, useEffect, useRef } from "react";

export const useCenteredTree = (): [RefObject<HTMLDivElement | null>, { x: number; y: number }, { siblings: number; nonSiblings: number }] => {
    const [translate, setTranslate] = useState({ x: 0, y: 0 });
    const [separation, setSeparation] = useState({ siblings: 1, nonSiblings: 1 });
    const containerRef = useRef<HTMLDivElement | null>(null);

    const handleResize = useCallback(() => {
        if (containerRef.current) {
            const dimensions = containerRef.current.getBoundingClientRect();
            setTranslate({ x: dimensions.width / 2, y: dimensions.height / 4 });

            // Guard against divide-by-zero and clamp to reasonable bounds
            const safeWidth = Math.max(dimensions.width, 1);
            const rawNonSiblings = dimensions.height / (safeWidth * 0.5);

            setSeparation({
                siblings: Math.max(0.5, Math.min(2, 1)), // Clamp between 0.5 and 2
                nonSiblings: Math.max(0.2, Math.min(3, rawNonSiblings)), // Clamp between 0.2 and 3
            });
        }
    }, []);

    useEffect(() => {
        handleResize();
        window.addEventListener("resize", handleResize);
        return () => window.removeEventListener("resize", handleResize);
    }, [handleResize]);

    return [containerRef, translate, separation];
};