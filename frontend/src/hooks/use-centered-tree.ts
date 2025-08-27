import { useState, useCallback, type RefObject, useEffect, useRef } from "react";

export const useCenteredTree = (): [RefObject<HTMLDivElement | null>, { x: number; y: number }, { siblings: number; nonSiblings: number }] => {
    const [translate, setTranslate] = useState({ x: 0, y: 0 });
    const [separation, setSeparation] = useState({ siblings: 1, nonSiblings: 1 });
    const containerRef = useRef<HTMLDivElement>(null);

    const handleResize = useCallback(() => {
        if (containerRef.current) {
            const dimensions = containerRef.current.getBoundingClientRect();
            setTranslate({ x: dimensions.width / 2, y: dimensions.height / 4 });
            setSeparation({
                siblings: 1, // Previously x: 1
                nonSiblings: dimensions.height / (dimensions.width * 0.5), // Previously y
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