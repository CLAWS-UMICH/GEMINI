import { useState, useEffect } from "react";

export function getRandomIntInclusive(min: number, max: number): number {
    const minCeiled: number = Math.ceil(min);
    const maxFloored: number = Math.floor(max);
    return Math.floor(Math.random() * (maxFloored - minCeiled + 1)) + minCeiled; 
}

export function useRandomIntInclusive(min: number, max: number): number {
    const [value, setValue] = useState(() => getRandomIntInclusive(min, max));

    useEffect(() => {
        const interval = setInterval(() => {
            setValue(getRandomIntInclusive(min, max));
        }, 1000);
        return () => clearInterval(interval);
    }, [min, max]);

    return value;
}