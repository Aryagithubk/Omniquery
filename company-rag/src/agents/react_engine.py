import re
import json
import logging
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class Tool:
    name: str
    description: str
    func: Callable

class ReActEngine:
    """
    A lightweight, regex-based Custom ReAct loop engine designed to be highly 
    forgiving of small local LLMs formatting quirks when tool-calling.
    """
    
    def __init__(self, llm, tools: List[Tool], max_iterations: int = 5):
        self.llm = llm
        self.tools = {tool.name: tool for tool in tools}
        self.max_iterations = max_iterations
        
    def _format_tool_descriptions(self) -> str:
        tool_desc = []
        for name, tool in self.tools.items():
            tool_desc.append(f"- {name}: {tool.description}")
        return "\n".join(tool_desc)
        
    def _parse_action(self, response_text: str) -> tuple[Optional[str], Optional[str]]:
        """
        Parses the text for:
        Action: tool_name
        Action Input: {"param": "value"}
        Returns (tool_name, tool_input). If not found, returns None, None.
        """
        # Try to parse strict Action / Action Input first
        action_match = re.search(r"Action:\s*(.*?)\n", response_text, re.IGNORECASE)
        input_match = re.search(r"Action Input:\s*(.*?)(?:\n|$)", response_text, re.IGNORECASE | re.DOTALL)
        
        if action_match and input_match:
            action = action_match.group(1).strip().lower()
            action_input = input_match.group(1).strip()
            # Clean possible markdown json wrapper
            action_input = re.sub(r"^```json", "", action_input)
            action_input = re.sub(r"^```", "", action_input)
            action_input = re.sub(r"```$", "", action_input).strip()
            return action, action_input
            
        return None, None

    def _extract_final_answer(self, response_text: str) -> Optional[str]:
        match = re.search(r"Final Answer:\s*(.*?)(?:\n|$)", response_text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # If it doesn't say "Final Answer", but it didn't call an action either, the whole text might be the answer
        return None

    async def execute(self, system_prompt: str, user_query: str) -> str:
        """Executes the ReAct loop until Final Answer or max_iterations is reached."""
        context_window = ""
        
        base_prompt = (
            f"{system_prompt}\n\n"
            f"You have access to the following tools:\n"
            f"{self._format_tool_descriptions()}\n\n"
            f"To answer the user, you must use the following strict format:\n"
            f"Thought: <explain what you need to do>\n"
            f"Action: <the tool name to use, one of [{', '.join(self.tools.keys())}]>\n"
            f"Action Input: <a valid JSON object containing the parameters for the tool>\n"
            f"Observation: <the result of the tool, provided by the system>\n"
            f"... (this Thought/Action/Action Input/Observation can repeat N times)\n"
            f"Thought: I know the final answer.\n"
            f"Final Answer: <the final response to the user>\n\n"
            f"Begin!\n"
            f"Question: {user_query}\n"
        )
        
        for iteration in range(self.max_iterations):
            if iteration == 0:
                current_prompt = f"{base_prompt}Thought: "
            else:
                current_prompt = f"{base_prompt}Thought: {context_window}"
            
            logger.info(f"ReAct Iteration {iteration+1}. Calling LLM...")
            
            llm_response = await self.llm.generate(current_prompt)
            response_text = llm_response.text if hasattr(llm_response, 'text') else str(llm_response)
            
            logger.debug(f"LLM Response:\n{response_text}")
            
            # Check for Final Answer
            final_answer = self._extract_final_answer(response_text)
            if final_answer:
                return final_answer
                
            # Log the thought process but we only parse the action
            action, action_input = self._parse_action(response_text)
            
            if action:
                context_window += f"{response_text}"
                
                if action not in self.tools:
                    obs = f"Error: Tool '{action}' not found. Available tools: {list(self.tools.keys())}."
                else:
                    try:
                        param_dict = json.loads(action_input) if action_input else {}
                        logger.info(f"Executing tool '{action}' with inputs: {param_dict}")
                        obs = self.tools[action].func(**param_dict)
                    except json.JSONDecodeError:
                        obs = f"Error: Action Input is not valid JSON. Ensure you pass a valid JSON object like {{\"key\": \"value\"}}."
                    except Exception as e:
                        obs = f"Error running tool '{action}': {str(e)}"
                
                if "Mutation executed successfully" in obs:
                    try:
                        return json.loads(obs).get("message", "Database effectively updated.")
                    except:
                        return obs

                # SHORT CIRCUIT: If tool returned a massive markdown table payload
                # (e.g. from get_employee_record or execute_custom_select)
                # don't force the small LLM to echo it. Just return it immediately as the final response!
                try:
                    obs_dict = json.loads(obs)
                    if obs_dict.get("status") == "success" and "markdown" in obs_dict:
                        logger.info("Intercepted markdown payload from tool. Short-circuiting ReAct loop!")
                        return obs_dict.get("markdown", "")
                except:
                    pass

                logger.info(f"Observation: {obs}")
                context_window += f"\nObservation: {obs}\nThought: "
            else:
                # If no Action and no Final Answer could be parsed, force LLM to either take action or give Final Answer
                if iteration == self.max_iterations - 1:
                    break
                context_window += f"{response_text}\nObservation: Error! You must either use 'Action:' to use a tool, or 'Final Answer:' to respond to the user. Try again.\nThought: "
        
        # If we exit the loop
        return "I could not determine the answer within the allowed iterations. Please be more specific or try a different question."
